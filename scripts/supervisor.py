#!/usr/bin/env python3
"""
Bot Supervisor - 从 MySQL 动态管理多个 bot 进程
自动读取 bot_tokens 表，启动所有 bot
"""

import os
import sys
import time
import signal
import subprocess
import logging
import hashlib
import urllib.request
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [supervisor] %(message)s",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = 5
API_PORT_BASE = 15001
TMUX_SOCKET = os.getenv("TMUX_SOCKET", f"/tmp/tmux-{os.getuid()}/default")

# {token_hash: {"proc", "ttyd_proc", "ttyd_port", "token", "bot_name", "session", "port"}}
bots: dict[str, dict] = {}
handler_proc = None
api_proc = None


def fetch_bot_name(token: str) -> str:
    """从 Telegram API 获取 bot username"""
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                return data["result"].get("username", "unknown_bot")
    except Exception as e:
        logger.error(f"获取 bot name 失败: {e}")
    return f"bot_{hashlib.md5(token.encode()).hexdigest()[:8]}"


def token_key(token: str) -> str:
    return hashlib.md5(token.encode()).hexdigest()[:12]


def ensure_tmux_session(session_name: str):
    """确保 tmux session 存在，不存在则创建"""
    check = subprocess.run(
        ["tmux", "-S", TMUX_SOCKET, "has-session", "-t", session_name],
        capture_output=True,
    )
    if check.returncode != 0:
        subprocess.run(
            ["tmux", "-S", TMUX_SOCKET, "new-session", "-d", "-s", session_name, "-n", "master"],
            capture_output=True,
        )
        logger.info(f"📺 创建 tmux session: {session_name}")


def ensure_tmux_window(group: str, bot_name: str, workspace: str = "") -> str:
    """确保 group session 里有 bot_name window，返回 win_id"""
    ensure_tmux_session(group)
    # 检查 window 是否存在
    check = subprocess.run(
        ["tmux", "-S", TMUX_SOCKET, "list-windows", "-t", group, "-F", "#{window_name}"],
        capture_output=True, text=True,
    )
    windows = check.stdout.strip().split("\n") if check.stdout.strip() else []
    created = False
    if bot_name not in windows:
        # 如果只有默认 master window 且是空的，重命名它
        if len(windows) == 1 and windows[0] == "master":
            subprocess.run(
                ["tmux", "-S", TMUX_SOCKET, "rename-window", "-t", f"{group}:master", bot_name],
                capture_output=True,
            )
        else:
            subprocess.run(
                ["tmux", "-S", TMUX_SOCKET, "new-window", "-t", group, "-n", bot_name],
                capture_output=True,
            )
        created = True
        logger.info(f"📺 创建 window: {group}:{bot_name}")
    win_id = f"{group}:{bot_name}.0"  # 完整格式: session:window.pane
    # 只在新建 window 时才发送 init 命令
    if created:
        wd = workspace or f"~/workers/{bot_name}"
        init_cmd = (
            f"mkdir -p {wd}/.kiro/steering && "
            f"for f in ~/workers/.template/*.md; do "
            f"t={wd}/.kiro/steering/$(basename $f); "
            f"[ ! -f $t ] && sed 's/{{{{BOT_NAME}}}}/{bot_name}/g' $f > $t; "
            f"done; cd {wd} && kiro-cli"
        )
        subprocess.run(
            ["tmux", "-S", TMUX_SOCKET, "send-keys", "-t", win_id, init_cmd, "Enter"],
            capture_output=True,
        )
    return win_id


router_proc = None


def start_router():
    global router_proc
    proc = subprocess.Popen(
        [sys.executable, "-u", "scripts/bot_router.py"],
        stdout=open("/tmp/bot_router.log", "w"),
        stderr=subprocess.STDOUT,
    )
    logger.info(f"✅ 启动 Router (pid={proc.pid})")
    router_proc = proc


def parse_conf() -> list[dict] | None:
    """从 MySQL bot_config 读取 bot 列表（只读取 status='active' 的）"""
    try:
        import pymysql
        mysql_pass = os.getenv("MYSQL_PASSWORD", "")
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password=mysql_pass,
            database='tts_bot',
            charset='utf8mb4'
        )
        c = conn.cursor()
        c.execute("SELECT bot_name, bot_token, group_name, workspace FROM bot_config WHERE status='active'")
        rows = c.fetchall()
        c.close()
        conn.close()
        
        if not rows:
            return None
            
        entries = []
        for bot_name, token, group, workspace in rows:
            entries.append({
                "bot_name": bot_name,
                "token": token,
                "group": group or "worker",
                "workspace": workspace or ""
            })
        
        return entries if entries else None
    except Exception as e:
        logger.error(f"❌ 从 MySQL 读取 bot 列表失败: {e}")
        return None


def conf_hash() -> str:
    """计算 MySQL bot_config 表的 hash"""
    try:
        import pymysql
        mysql_pass = os.getenv("MYSQL_PASSWORD", "")
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password=mysql_pass,
            database='tts_bot',
            charset='utf8mb4'
        )
        c = conn.cursor()
        c.execute("SELECT bot_name, bot_token, status FROM bot_config ORDER BY bot_name")
        rows = c.fetchall()
        c.close()
        conn.close()
        
        content = "\n".join(f"{name},{token},{status}" for name, token, status in rows)
        return hashlib.md5(content.encode()).hexdigest()
    except Exception as e:
        logger.error(f"❌ 计算 hash 失败: {e}")
        return ""


def start_ttyd(bot_name: str, win_id: str, base_port: int = 16000):
    """为 bot 启动 ttyd 实例（带 token 认证）
    端口固定分配：
      master  → 16000
      auth    → 16001
      worker  → 16002
    """
    import secrets, json, pymysql, requests

    # 固定端口映射（按 group 顺序）
    FIXED_PORTS = {
        "cicy_master_xk_bot": 16000,
        "cicy_test_final_bot": 16001,
        "cicy_test_auto_bot": 16002,
    }
    port = FIXED_PORTS.get(bot_name)
    if port is None:
        # 未知 bot，从 16010 开始按 bot_config.id 分配
        try:
            mysql_pass = os.getenv("MYSQL_PASSWORD", "")
            conn = pymysql.connect(host='localhost', user='root', password=mysql_pass, database='tts_bot', autocommit=True)
            c = conn.cursor()
            c.execute("SELECT id FROM bot_config WHERE bot_name=%s", (bot_name,))
            row = c.fetchone()
            conn.close()
            port = 16010 + (row[0] if row else 0)
        except:
            port = base_port + 99

    # 先杀掉占用该端口的旧 ttyd
    subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
    import time
    time.sleep(0.5)

    # 生成随机 token 作为密码
    token = secrets.token_urlsafe(16)

    # 启动 ttyd（只读模式）
    proc = subprocess.Popen(
        ["ttyd", "-p", str(port), "-c", f"bot:{token}", "-R",
         "tmux", "-S", TMUX_SOCKET, "attach-session", "-t", win_id],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info(f"✅ 启动 ttyd: {bot_name} (port={port}, win_id={win_id}, pid={proc.pid})")

    # 保存到 bot_config 表
    try:
        mysql_pass = os.getenv("MYSQL_PASSWORD", "")
        conn = pymysql.connect(host='localhost', user='root', password=mysql_pass, database='tts_bot', autocommit=True)
        c = conn.cursor()
        c.execute("""
            UPDATE bot_config
            SET ttyd_port=%s, ttyd_token=%s
            WHERE bot_name=%s
        """, (port, token, bot_name))
        c.close()
        conn.close()
        logger.info(f"✅ 保存 ttyd: {bot_name} port={port}")
    except Exception as e:
        logger.error(f"❌ 保存 ttyd 信息失败: {e}")

    return proc, port


def start_bot(token: str, bot_name: str, group: str, win_id: str, port: int):
    """启动一个 bot 进程"""
    proc = subprocess.Popen(
        [sys.executable, "-m", "tts_bot.bot", "--bot-name", bot_name],
        stdout=open(f"/tmp/bot_{bot_name}.log", "w"),
        stderr=subprocess.STDOUT,
    )
    logger.info(f"✅ 启动 bot: {bot_name} (group={group}, win_id={win_id}, port={port}, pid={proc.pid})")
    
    # 启动对应的 ttyd
    ttyd_proc, ttyd_port = start_ttyd(bot_name, win_id)
    
    return proc, ttyd_proc, ttyd_port


def stop_bot(key: str):
    """停止一个 bot 和对应的 ttyd"""
    if key in bots:
        info = bots[key]
        # 停止 bot 进程
        if info["proc"].poll() is None:
            info["proc"].terminate()
            try:
                info["proc"].wait(timeout=5)
            except subprocess.TimeoutExpired:
                info["proc"].kill()
        # 停止 ttyd 进程
        if "ttyd_proc" in info and info["ttyd_proc"].poll() is None:
            info["ttyd_proc"].terminate()
            try:
                info["ttyd_proc"].wait(timeout=3)
            except subprocess.TimeoutExpired:
                info["ttyd_proc"].kill()
        logger.info(f"❌ 停止 bot: {info['bot_name']}")
        del bots[key]


def start_api():
    global api_proc
    proc = subprocess.Popen(
        [sys.executable, "scripts/bot_api.py"],
        stdout=open("/tmp/bot_api.log", "w"),
        stderr=subprocess.STDOUT,
    )
    logger.info(f"✅ 启动 API (pid={proc.pid})")
    api_proc = proc


def start_handler():
    global handler_proc
    proc = subprocess.Popen(
        [sys.executable, "-u", "scripts/qa_matcher.py"],
        stdout=open("/tmp/qa_matcher.log", "a"),
        stderr=subprocess.STDOUT,
    )
    logger.info(f"✅ 启动 QA Matcher (pid={proc.pid})")
    handler_proc = proc


def sync_bots():
    """同步配置和运行中的 bot"""
    entries = parse_conf()

    # 配置不存在或为空 → 保持现状，只守护
    if entries is None:
        for key, info in list(bots.items()):
            if info["proc"].poll() is not None:
                logger.warning(f"⚠️ {info['bot_name']} 崩溃，重启...")
                proc, ttyd_proc, ttyd_port = start_bot(info["token"], info["bot_name"], info["group"], info["win_id"], info["port"])
                info["proc"] = proc
                info["ttyd_proc"] = ttyd_proc
                info["ttyd_port"] = ttyd_port
        return

    conf_keys = set()

    for entry in entries:
        bot_name = entry["bot_name"]
        token = entry["token"]
        group = entry["group"]
        workspace = entry.get("workspace", "")
        key = bot_name

        conf_keys.add(key)

        # 新增的 bot
        if key not in bots:
            win_id = ensure_tmux_window(group, bot_name, workspace)
            port = int(os.environ.get("API_PORT", 15001))
            proc, ttyd_proc, ttyd_port = start_bot(token, bot_name, group, win_id, port)
            bots[key] = {
                "proc": proc,
                "ttyd_proc": ttyd_proc,
                "ttyd_port": ttyd_port,
                "token": token,
                "bot_name": bot_name,
                "group": group,
                "win_id": win_id,
                "port": port,
            }
        # token 变化的 bot - 只重启这个
        elif bots[key]["token"] != token:
            logger.info(f"🔄 {bot_name} token 变化，重启...")
            stop_bot(key)
            win_id = ensure_tmux_window(group, bot_name, workspace)
            port = int(os.environ.get("API_PORT", 15001))
            proc, ttyd_proc, ttyd_port = start_bot(token, bot_name, group, win_id, port)
            bots[key] = {
                "proc": proc,
                "ttyd_proc": ttyd_proc,
                "ttyd_port": ttyd_port,
                "token": token,
                "bot_name": bot_name,
                "group": group,
                "win_id": win_id,
                "port": port,
            }

    # 停止已移除的
    for key in set(bots.keys()) - conf_keys:
        stop_bot(key)

    # 守护崩溃的
    for key, info in list(bots.items()):
        if info["proc"].poll() is not None:
            logger.warning(f"⚠️ {info['bot_name']} 崩溃，重启...")
            proc, ttyd_proc, ttyd_port = start_bot(info["token"], info["bot_name"], info["group"], info["win_id"], info["port"])
            info["proc"] = proc
            info["ttyd_proc"] = ttyd_proc
            info["ttyd_port"] = ttyd_port


def cleanup(signum, frame):
    logger.info("🛑 停止中...")
    for key in list(bots.keys()):
        stop_bot(key)
    if handler_proc and handler_proc.poll() is None:
        handler_proc.terminate()
    if router_proc and router_proc.poll() is None:
        router_proc.terminate()
    if api_proc and api_proc.poll() is None:
        api_proc.terminate()
    sys.exit(0)


def main():
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    logger.info("=" * 50)
    logger.info("🚀 Bot Supervisor 启动")
    logger.info(f"📋 数据源: MySQL bot_config 表")
    logger.info("=" * 50)

    start_api()

    # 等待 MySQL 有数据
    while True:
        entries = parse_conf()
        if entries:
            logger.info(f"✅ 发现 {len(entries)} 个 bot 配置")
            break
        logger.info("⏳ 等待 MySQL bot_tokens 表有数据...")
        time.sleep(5)

    # 先启动 bot（注册 session_map），再启动 handler
    last_hash = conf_hash()
    sync_bots()

    # bot 注册需要几秒
    import time as _t
    _t.sleep(5)
    start_handler()
    # router 已移到宿主机 node.js 运行
    # start_router()

    while True:
        current_hash = conf_hash()
        if current_hash != last_hash:
            logger.info("📋 MySQL 配置变化，重新加载...")
            sync_bots()
            last_hash = current_hash

        # 守护 handler 和 api
        if handler_proc and handler_proc.poll() is not None:
            logger.warning("⚠️ Handler 崩溃，重启...")
            start_handler()
        if api_proc and api_proc.poll() is not None:
            logger.warning("⚠️ API 崩溃，重启...")
            start_api()
        # router 已移到宿主机 node.js 运行
        # if router_proc and router_proc.poll() is not None:
        #     logger.warning("⚠️ Router 崩溃，重启...")
        #     start_router()

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
