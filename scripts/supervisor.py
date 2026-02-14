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


TTYD_PORT_BASE = 7680

# {session_name: {"proc": Popen, "port": int}}
ttyd_procs: dict[str, dict] = {}
_used_ports: set[int] = set()

def _alloc_port() -> int:
    """分配一个可用端口"""
    port = TTYD_PORT_BASE
    while port in _used_ports:
        port += 1
    _used_ports.add(port)
    return port

def _free_port(port: int):
    """释放端口"""
    _used_ports.discard(port)

def ensure_ttyd(session_name: str) -> int:
    """确保 session 有对应的 ttyd，返回端口"""
    global _next_ttyd_port
    if session_name in ttyd_procs and ttyd_procs[session_name]["proc"].poll() is None:
        return ttyd_procs[session_name]["port"]

    port = _alloc_port()

    proc = subprocess.Popen(
        ["ttyd", "-p", str(port), "-W",
         "-c", "admin:pb200898",
         "--base-path", f"/{session_name}",
         "tmux", "-S", TMUX_SOCKET, "attach-session", "-t", session_name],
        stdout=open(f"/tmp/ttyd_{session_name}.log", "w"),
        stderr=subprocess.STDOUT,
    )
    ttyd_procs[session_name] = {"proc": proc, "port": port}
    logger.info(f"📺 启动 ttyd: /{session_name} → :{port} (pid={proc.pid})")
    # 更新 nginx 配置
    update_nginx()
    return port


def update_nginx():
    """根据当前 ttyd 实例更新 nginx 配置"""
    locations = ""
    for name, info in ttyd_procs.items():
        if info["proc"].poll() is None:
            port = info["port"]
            locations += f"""
        location /{name}/ {{
            if ($arg_token != "pb200898") {{
                return 403;
            }}
            proxy_pass http://127.0.0.1:{port}/{name}/;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_set_header Host $host;
            proxy_read_timeout 86400;
        }}

        location = /{name} {{
            return 302 /{name}/?token=$arg_token;
        }}
"""

    conf = f"""error_log /tmp/nginx_error.log;
pid /tmp/nginx.pid;

events {{
    worker_connections 1024;
}}

http {{
    access_log /tmp/nginx_access.log;

    map $http_upgrade $connection_upgrade {{
        default upgrade;
        '' close;
    }}

    server {{
        listen 12345;
        server_name _;
{locations}
    }}
}}
"""
    conf_path = "/tmp/nginx_dynamic.conf"
    with open(conf_path, "w") as f:
        f.write(conf)
    subprocess.run(["nginx", "-s", "reload", "-c", conf_path], capture_output=True)
    logger.info(f"🔄 Nginx 配置已更新 ({len(ttyd_procs)} sessions)")


def parse_conf() -> list[dict] | None:
    """解析 bots.conf"""
    if not os.path.exists(CONF_PATH):
        return None
    entries = []
    with open(CONF_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",", 1)
            token = parts[0].strip()
            session = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ""
            if not token:
                continue
            entries.append({"token": token, "session": session})
    return entries if entries else None


def conf_hash() -> str:
    if not os.path.exists(CONF_PATH):
        return ""
    with open(CONF_PATH, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def start_bot(token: str, bot_name: str, session: str, port: int):
    """启动一个 bot 进程"""
    env = os.environ.copy()
    env["BOT_TOKEN"] = token
    env["BOT_NAME"] = bot_name
    env["TMUX_SESSION"] = session
    env["API_PORT"] = str(port)

    proc = subprocess.Popen(
        [sys.executable, "-m", "tts_bot.bot"],
        env=env,
        stdout=open(f"/tmp/bot_{bot_name}.log", "w"),
        stderr=subprocess.STDOUT,
    )
    logger.info(f"✅ 启动 bot: {bot_name} (session={session}, port={port}, pid={proc.pid})")
    return proc


def stop_bot(key: str):
    """停止一个 bot 及其 ttyd"""
    if key in bots:
        info = bots[key]
        session = info["session"]
        # 停 bot
        if info["proc"].poll() is None:
            info["proc"].terminate()
            try:
                info["proc"].wait(timeout=5)
            except subprocess.TimeoutExpired:
                info["proc"].kill()
        # 停 ttyd
        if session in ttyd_procs:
            ttyd_info = ttyd_procs[session]
            if ttyd_info["proc"].poll() is None:
                ttyd_info["proc"].terminate()
            _free_port(ttyd_info["port"])
            del ttyd_procs[session]
            logger.info(f"♻️ 回收 ttyd: /{session} (port={ttyd_info['port']})")
            update_nginx()
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
    entries = parse_conf()

    # 配置不存在或为空 → 保持现状，只守护
    if entries is None:
        for key, info in list(bots.items()):
            if info["proc"].poll() is not None:
                logger.warning(f"⚠️ {info['bot_name']} 崩溃，重启...")
                info["proc"] = start_bot(info["token"], info["bot_name"], info["session"], info["port"])
        return

    conf_keys = set()
    port = API_PORT_BASE

    for entry in entries:
        key = token_key(entry["token"])
        conf_keys.add(key)

        if key not in bots:
            # 新 bot：获取 name，确定 session
            if entry["session"]:
                session = entry["session"]
                bot_name = session
            else:
                bot_name = fetch_bot_name(entry["token"])
                session = bot_name.replace("@", "").replace("_bot", "").replace("Bot", "")

            ensure_tmux_session(session)
            ensure_ttyd(session)
            proc = start_bot(entry["token"], bot_name, session, port)
            bots[key] = {
                "proc": proc,
                "token": entry["token"],
                "bot_name": bot_name,
                "session": session,
                "port": port,
            }
        port += 1

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
    start_handler()

    last_hash = ""
    while True:
        current_hash = conf_hash()
        if current_hash != last_hash:
            if last_hash:
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

        # 回收死掉的 ttyd，释放端口
        for name in list(ttyd_procs.keys()):
            info = ttyd_procs[name]
            if info["proc"].poll() is not None:
                port = info["port"]
                _free_port(port)
                del ttyd_procs[name]
                logger.info(f"♻️ 回收 ttyd: /{name} (port={port})")
                # 如果 bot 还在运行，重新启动 ttyd
                for key, bot_info in bots.items():
                    if bot_info["session"] == name and bot_info["proc"].poll() is None:
                        ensure_ttyd(name)
                        break

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
