#!/usr/bin/env python3
"""
Kiro-CLI 回复捕获器
轮询 tmux，检测回复完成后调 /reply API 发回用户
"""

import asyncio
import logging
import os
import sys
import aiohttp
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tts_bot.config import config
from tts_bot.kiro_tmux_backend import KiroTmuxBackend

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DATA_DIR = os.getenv("DATA_DIR", os.path.expanduser("~/data/tts-tg-bot"))
API_URL = f"http://localhost:{os.getenv('API_PORT', '15001')}"

tmux = KiroTmuxBackend()
last_snapshot = ""


def get_active_chat_id() -> int:
    try:
        return int(open(os.path.join(DATA_DIR, "active_chat_id")).read().strip())
    except Exception:
        return 0


def snapshot() -> str:
    return tmux.capture_pane(config.win_id, max_rows=80)


def extract_new_reply(old: str, new: str) -> str:
    """提取最新的 kiro-cli 回复（最后一个 > 块）"""
    new_lines = [l for l in new.strip().split("\n") if l.strip()]
    old_lines = [l for l in old.strip().split("\n") if l.strip()]

    # 找最后一个 > 开头的回复块
    reply_lines = []
    found = False
    for line in reversed(new_lines):
        s = line.strip()
        if s.startswith("λ >") or s.startswith("▸ Credits:"):
            if found:
                break
            continue
        if s.startswith("> "):
            reply_lines.insert(0, s[2:])
            found = True
        elif found:
            # 多行回复的续行
            reply_lines.insert(0, line.rstrip())

    if not reply_lines:
        return ""

    reply = "\n".join(reply_lines).strip()

    # 检查这个回复是否已经在旧内容中（避免重复发送）
    if reply in old:
        return ""

    return reply


def is_idle(content: str) -> bool:
    """kiro-cli 是否空闲（最后非空行是 λ >）"""
    for line in reversed(content.strip().split("\n")):
        s = line.strip()
        if not s:
            continue
        return s.startswith("λ >")
    return False


def content_changed(old: str, new: str) -> bool:
    """比较有效内容是否变化"""
    old_clean = [l for l in old.strip().split("\n") if l.strip()]
    new_clean = [l for l in new.strip().split("\n") if l.strip()]
    return old_clean != new_clean


async def send_reply(chat_id: int, text: str):
    """调 /reply API 发回用户"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_URL}/reply", json={
                "message_id": "",
                "reply": text,
                "chat_id": chat_id,
            }) as resp:
                result = await resp.json()
                logger.info(f"回复已发送: {result}")
    except Exception as e:
        logger.error(f"调 /reply 失败: {e}")


async def main():
    global last_snapshot

    print("=" * 50)
    print("🔄 Kiro 回复捕获器（API 模式）")
    print(f"🎯 win_id: {config.win_id}")
    print(f"📡 API: {API_URL}/reply")
    print("=" * 50)

    last_snapshot = snapshot()
    was_busy = False

    while True:
        try:
            await asyncio.sleep(2)

            current = snapshot()
            if not content_changed(last_snapshot, current):
                continue

            idle = is_idle(current)

            if not idle:
                was_busy = True
                last_snapshot = current
                continue

            if was_busy:
                reply = extract_new_reply(last_snapshot, current)
                if reply:
                    chat_id = get_active_chat_id()
                    if chat_id:
                        logger.info(f"回复: {reply[:80]}...")
                        await send_reply(chat_id, reply)
                    else:
                        logger.warning("无 active_chat_id")
                was_busy = False

            last_snapshot = current

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"错误: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
