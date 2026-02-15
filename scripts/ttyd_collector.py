#!/usr/bin/env python3
"""
ttyd WebSocket 终端输出采集器
- 连接每个 bot 的 ttyd WebSocket
- 实时采集终端输出，写入 MySQL terminal_snapshot 表
- 替代 tmux capture-pane，避免 code hash bug
"""

import asyncio
import base64
import json
import logging
import os
import re
import signal
import sys
import time
from pathlib import Path

import pymysql
import websockets

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [collector] %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "tts_bot")

# 固定端口: master=16000, auth=16001, worker=16002
# 终端缓冲区最大行数
MAX_LINES = 500
# 写入 MySQL 间隔（秒）
FLUSH_INTERVAL = 1
# 重连间隔
RECONNECT_DELAY = 5

ANSI_RE = re.compile(
    r'\x1b\[[0-9;]*[a-zA-Z]'
    r'|\x1b\][^\x07]*\x07'
    r'|\x1b[()][AB012]'
    r'|\x1b[=>]'
    r'|\x0f|\r'
    r'|\x1b\[\?[0-9;]*[a-z]'
    r'|\x1b\[[0-9]*[;0-9]*[Hf]'  # cursor position
    r'|\x1b\[[0-9]*[ABCDJK]'     # cursor movement / erase
    r'|\x1b\[[0-9;]*m'           # SGR (color)
)


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub('', text)


def get_db():
    return pymysql.connect(
        host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE, charset='utf8mb4', autocommit=True
    )


def load_bots() -> list[dict]:
    """从 bot_config 加载所有有 ttyd_port 的 bot"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT bot_name, ttyd_port, ttyd_token
        FROM bot_config
        WHERE status='active' AND ttyd_port IS NOT NULL AND ttyd_port > 0
    """)
    bots = []
    for row in c.fetchall():
        bots.append({
            "bot_name": row[0],
            "port": row[1],
            "token": row[2] or "",
        })
    conn.close()
    return bots


def flush_snapshot(bot_name: str, lines: list[str]):
    """将当前缓冲区写入 MySQL snapshot"""
    content = "\n".join(lines)
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO terminal_snapshot (bot_name, content, line_count)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE content=%s, line_count=%s
        """, (bot_name, content, len(lines), content, len(lines)))
        conn.close()
    except Exception as e:
        logger.error(f"[{bot_name}] flush 失败: {e}")


async def collect_bot(bot_name: str, port: int, token: str):
    """连接一个 bot 的 ttyd，持续采集输出"""
    lines: list[str] = []
    last_flush = 0

    while True:
        try:
            cred = base64.b64encode(f"bot:{token}".encode()).decode()
            headers = [('Authorization', f'Basic {cred}')]
            ttyd_host = os.getenv("TTYD_HOST", "172.17.0.1")
            url = f'ws://{ttyd_host}:{port}/ws'

            logger.info(f"[{bot_name}] 连接 {url}")
            async with websockets.connect(
                url, subprotocols=['tty'],
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10,
            ) as ws:
                # ttyd 握手
                await ws.send(json.dumps({
                    "AuthToken": cred, "columns": 200, "rows": 50
                }))
                logger.info(f"[{bot_name}] 已连接")

                partial = ""
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    except asyncio.TimeoutError:
                        # 没有新数据，正常
                        now = time.time()
                        if now - last_flush >= FLUSH_INTERVAL and lines:
                            flush_snapshot(bot_name, lines)
                            last_flush = now
                        continue

                    if isinstance(msg, bytes) and len(msg) > 1 and chr(msg[0]) == '0':
                        # type '0' = terminal output
                        raw = msg[1:].decode('utf-8', errors='replace')
                        clean = strip_ansi(raw)
                        partial += clean

                        # 按换行分割
                        while '\n' in partial:
                            line, partial = partial.split('\n', 1)
                            line = line.strip()
                            if line:
                                lines.append(line)
                                if len(lines) > MAX_LINES:
                                    lines = lines[-MAX_LINES:]

                        # 定期 flush
                        now = time.time()
                        if now - last_flush >= FLUSH_INTERVAL:
                            flush_snapshot(bot_name, lines)
                            last_flush = now

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"[{bot_name}] 连接断开: {e}")
        except Exception as e:
            logger.error(f"[{bot_name}] 错误: {e}")

        logger.info(f"[{bot_name}] {RECONNECT_DELAY}秒后重连...")
        await asyncio.sleep(RECONNECT_DELAY)


async def main():
    bots = load_bots()
    if not bots:
        logger.error("没有找到配置了 ttyd 的 bot，退出")
        sys.exit(1)

    logger.info(f"启动采集器，{len(bots)} 个 bot:")
    for b in bots:
        logger.info(f"  - {b['bot_name']}: port={b['port']}")

    tasks = [collect_bot(b["bot_name"], b["port"], b["token"]) for b in bots]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    # 文件锁
    import fcntl
    lock_fd = open("/tmp/ttyd_collector.lock", "w")
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print("另一个 collector 已在运行，退出")
        sys.exit(0)
    asyncio.run(main())
