#!/usr/bin/env python3
"""
初始化 tmux windows + 启动 ttyd 实例
从 MySQL bot_config 读取配置，为每个 bot 创建 tmux window 并启动 ttyd
"""

import os
import sys
import subprocess
import logging
import secrets
import time

import pymysql

logging.basicConfig(level=logging.INFO, format="%(asctime)s [init_tmux] %(message)s")
log = logging.getLogger(__name__)

TMUX_SOCKET = os.getenv("TMUX_SOCKET", f"/tmp/tmux-{os.getuid()}/default")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")

# 固定 ttyd 端口
FIXED_PORTS = {
    "cicy_master_xk_bot": 16000,
    "cicy_test_final_bot": 16001,
    "cicy_test_auto_bot": 16002,
}


def db():
    return pymysql.connect(
        host="localhost", user="root", password=MYSQL_PASSWORD,
        database="tts_bot", charset="utf8mb4", autocommit=True
    )


def ensure_tmux_session(session_name: str):
    check = subprocess.run(
        ["tmux", "-S", TMUX_SOCKET, "has-session", "-t", session_name],
        capture_output=True,
    )
    if check.returncode != 0:
        subprocess.run(
            ["tmux", "-S", TMUX_SOCKET, "new-session", "-d", "-s", session_name, "-n", "master"],
            capture_output=True,
        )
        log.info(f"创建 tmux session: {session_name}")


def ensure_tmux_window(group: str, bot_name: str, workspace: str = "") -> str:
    ensure_tmux_session(group)
    check = subprocess.run(
        ["tmux", "-S", TMUX_SOCKET, "list-windows", "-t", group, "-F", "#{window_name}"],
        capture_output=True, text=True,
    )
    windows = check.stdout.strip().split("\n") if check.stdout.strip() else []
    created = False
    if bot_name not in windows:
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
        log.info(f"创建 window: {group}:{bot_name}")

    win_id = f"{group}:{bot_name}.0"
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


def start_ttyd(bot_name: str, win_id: str):
    port = FIXED_PORTS.get(bot_name, 16010)
    subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
    time.sleep(0.3)

    token = secrets.token_urlsafe(16)
    proc = subprocess.Popen(
        ["ttyd", "-p", str(port), "-c", f"bot:{token}", "-R",
         "tmux", "-S", TMUX_SOCKET, "attach-session", "-t", win_id],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    log.info(f"启动 ttyd: {bot_name} port={port} pid={proc.pid}")

    # 保存到 MySQL
    try:
        conn = db()
        c = conn.cursor()
        c.execute("UPDATE bot_config SET ttyd_port=%s, ttyd_token=%s WHERE bot_name=%s",
                  (port, token, bot_name))
        conn.close()
    except Exception as e:
        log.error(f"保存 ttyd 信息失败: {e}")

    return proc


def main():
    log.info("初始化 tmux windows + ttyd...")
    conn = db()
    c = conn.cursor()
    c.execute("SELECT bot_name, group_name, workspace FROM bot_config WHERE status='active'")
    rows = c.fetchall()
    conn.close()

    if not rows:
        log.error("没有找到 active 的 bot 配置")
        sys.exit(1)

    for bot_name, group, workspace in rows:
        group = group or "worker"
        win_id = ensure_tmux_window(group, bot_name, workspace or "")
        start_ttyd(bot_name, win_id)
        log.info(f"✅ {bot_name}: {win_id}")

    log.info(f"初始化完成，{len(rows)} 个 bot")


if __name__ == "__main__":
    main()
