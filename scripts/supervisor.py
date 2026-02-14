#!/usr/bin/env python3
"""
Bot Supervisor - 根据 bots.conf 动态管理多个 bot 进程
只需传 token，自动获取 bot name，自动创建 tmux session
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

CONF_PATH = os.getenv("BOTS_CONF", "/app/bots.conf")
POLL_INTERVAL = 5
API_PORT_BASE = 15001
TMUX_SOCKET = os.getenv("TMUX_SOCKET", f"/tmp/tmux-{os.getuid()}/default")

# {token_hash: {"proc", "token", "bot_name", "session", "port"}}
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
    win_id = f"{group}:{bot_name}"
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
    """解析 bots.conf — bot_name,group[,workspace] 格式"""
    if not os.path.exists(CONF_PATH):
        return None
    entries = []
    with open(CONF_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            bot_name = parts[0]
            group = parts[1] if len(parts) > 1 and parts[1] else "worker"
            workspace = parts[2] if len(parts) > 2 and parts[2] else ""
            if not bot_name:
                continue
            entries.append({"bot_name": bot_name, "group": group, "workspace": workspace})
    return entries if entries else None


def conf_hash() -> str:
    if not os.path.exists(CONF_PATH):
        return ""
    with open(CONF_PATH, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def start_bot(token: str, bot_name: str, group: str, win_id: str, port: int):
    """启动一个 bot 进程"""
    env = os.environ.copy()
    env["BOT_TOKEN"] = token
    env["BOT_NAME"] = bot_name
    env["TMUX_SESSION"] = group
    env["TMUX_WIN_ID"] = win_id
    env["API_PORT"] = str(port)

    proc = subprocess.Popen(
        [sys.executable, "-m", "tts_bot.bot"],
        env=env,
        stdout=open(f"/tmp/bot_{bot_name}.log", "w"),
        stderr=subprocess.STDOUT,
    )
    logger.info(f"✅ 启动 bot: {bot_name} (group={group}, win_id={win_id}, port={port}, pid={proc.pid})")
    return proc


def stop_bot(key: str):
    """停止一个 bot"""
    if key in bots:
        info = bots[key]
        if info["proc"].poll() is None:
            info["proc"].terminate()
            try:
                info["proc"].wait(timeout=5)
            except subprocess.TimeoutExpired:
                info["proc"].kill()
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
        [sys.executable, "-u", "scripts/kiro_handler.py"],
        stdout=open("/tmp/handler.log", "w"),
        stderr=subprocess.STDOUT,
    )
    logger.info(f"✅ 启动 Handler (pid={proc.pid})")
    handler_proc = proc


def sync_bots():
    """同步配置和运行中的 bot"""
    from token_manager import ensure_token

    entries = parse_conf()

    # 配置不存在或为空 → 保持现状，只守护
    if entries is None:
        for key, info in list(bots.items()):
            if info["proc"].poll() is not None:
                logger.warning(f"⚠️ {info['bot_name']} 崩溃，重启...")
                info["proc"] = start_bot(info["token"], info["bot_name"], info["session"], info["port"])
        return

    conf_keys = set()

    for entry in entries:
        bot_name = entry["bot_name"]
        group = entry["group"]
        workspace = entry.get("workspace", "")
        key = bot_name

        conf_keys.add(key)

        if key not in bots:
            token = ensure_token(bot_name)
            if not token:
                logger.error(f"❌ {bot_name}: 无法获取 token，跳过")
                continue

            win_id = ensure_tmux_window(group, bot_name, workspace)
            port = int(os.environ.get("API_PORT", 15001))
            proc = start_bot(token, bot_name, group, win_id, port)
            bots[key] = {
                "proc": proc,
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
            info["proc"] = start_bot(info["token"], info["bot_name"], info["session"], info["port"])


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
    logger.info(f"📋 配置: {CONF_PATH}")
    logger.info("=" * 50)

    start_api()

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
            logger.info("📋 配置变化，同步中...")
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
