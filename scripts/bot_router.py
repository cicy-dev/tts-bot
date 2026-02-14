#!/usr/bin/env python3
"""
Bot Router - nginx 动态反代 + ttyd 进程管理
访问 /<bot_name> → 查 session_map → 启动 ttyd → nginx 反代
"""

import os
import sys
import signal
import subprocess
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tts_bot.session_map import session_map

logging.basicConfig(level=logging.INFO, format="%(asctime)s [router] %(message)s")
logger = logging.getLogger(__name__)

TMUX_SOCKET = os.getenv("TMUX_SOCKET", f"/tmp/tmux-{os.getuid()}/default")
AUTH_TOKEN = os.getenv("ROUTER_TOKEN", "pb200898")
PORT = int(os.getenv("ROUTER_PORT", "12345"))
TTYD_BASE_PORT = 17000
NGINX_CONF = "/tmp/nginx_dynamic.conf"
NGINX_PID = "/tmp/nginx.pid"

# bot_name → {"proc": Popen, "port": int, "win_id": str}
ttyd_instances: dict[str, dict] = {}
_next_port = TTYD_BASE_PORT


def alloc_port() -> int:
    global _next_port
    p = _next_port
    _next_port += 1
    return p


def start_ttyd(bot_name: str, win_id: str) -> int:
    if bot_name in ttyd_instances:
        info = ttyd_instances[bot_name]
        if info["proc"].poll() is None:
            return info["port"]
        del ttyd_instances[bot_name]

    port = alloc_port()
    proc = subprocess.Popen(
        ["ttyd", "-p", str(port), "-W", "-i", "127.0.0.1",
         "-b", f"/{bot_name}",
         "tmux", "-S", TMUX_SOCKET, "attach-session", "-t", win_id],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    ttyd_instances[bot_name] = {"proc": proc, "port": port, "win_id": win_id}
    logger.info(f"🚀 ttyd started: /{bot_name} → :{port} → {win_id} (pid={proc.pid})")
    return port


def stop_all():
    for name, info in ttyd_instances.items():
        if info["proc"].poll() is None:
            info["proc"].terminate()
    ttyd_instances.clear()


def write_nginx_conf():
    """根据当前 ttyd_instances 生成 nginx 配置并 reload"""
    locations = []
    for bot_name, info in ttyd_instances.items():
        if info["proc"].poll() is not None:
            continue
        port = info["port"]
        locations.append(f"""
        location /{bot_name}/ {{
            if ($arg_token != "{AUTH_TOKEN}") {{
                return 403;
            }}
            proxy_pass http://127.0.0.1:{port}/{bot_name}/;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_set_header Host $host;
            proxy_read_timeout 86400;
        }}

        location = /{bot_name} {{
            return 302 /{bot_name}/?token=$arg_token;
        }}""")

    # 首页：列出所有 bot
    index_body = "<h3>Bot Router</h3><ul>"
    for bot_name in ttyd_instances:
        index_body += f'<li><a href="/{bot_name}/?token={AUTH_TOKEN}">{bot_name}</a></li>'
    index_body += "</ul>"

    conf = f"""error_log /tmp/nginx_error.log;
pid {NGINX_PID};

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
        listen {PORT};
        server_name _;

        location = / {{
            default_type text/html;
            return 200 '{index_body}';
        }}
{"".join(locations)}
    }}
}}"""

    Path(NGINX_CONF).write_text(conf)
    logger.info(f"📝 nginx conf written: {len(ttyd_instances)} bots")


def start_nginx():
    """启动或 reload nginx"""
    # 先杀旧的
    subprocess.run(["pkill", "-f", f"nginx.*{NGINX_CONF}"], capture_output=True)
    time.sleep(0.5)
    r = subprocess.run(["nginx", "-c", NGINX_CONF], capture_output=True, text=True)
    if r.returncode == 0:
        logger.info("✅ nginx started")
    else:
        logger.error(f"❌ nginx start failed: {r.stderr}")


def reload_nginx():
    r = subprocess.run(["nginx", "-c", NGINX_CONF, "-s", "reload"], capture_output=True, text=True)
    if r.returncode == 0:
        logger.info("🔄 nginx reloaded")
    else:
        logger.error(f"❌ nginx reload failed: {r.stderr}")


def ensure_bots():
    """扫描 session_map，为每个 bot 启动 ttyd"""
    mapping = session_map.get_all()
    changed = False
    for win_id, info in mapping.items():
        bot_name = info["bot_name"]
        if bot_name not in ttyd_instances or ttyd_instances[bot_name]["proc"].poll() is not None:
            start_ttyd(bot_name, win_id)
            time.sleep(1)  # 等 ttyd 启动
            changed = True
    # 清理已死的
    dead = [n for n, i in ttyd_instances.items() if i["proc"].poll() is not None]
    for n in dead:
        del ttyd_instances[n]
        changed = True
    return changed


def main():
    signal.signal(signal.SIGTERM, lambda *_: (stop_all(), sys.exit(0)))
    logger.info(f"🌐 Bot Router starting on :{PORT}")

    # 首次启动：扫描所有 bot，启动 ttyd，写 nginx 配置
    ensure_bots()
    write_nginx_conf()
    start_nginx()

    # 主循环：定期检查新 bot 和 ttyd 健康
    while True:
        time.sleep(10)
        if ensure_bots():
            write_nginx_conf()
            reload_nginx()


if __name__ == "__main__":
    main()
