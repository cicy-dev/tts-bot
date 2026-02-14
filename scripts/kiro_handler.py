#!/usr/bin/env python3
"""
Kiro-CLI 回复捕获器
多线程捕获 tmux，异步高并发重试发送 /reply
"""

import asyncio
import logging
import os
import sys
import hashlib
import aiohttp
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).parent.parent))

from tts_bot.config import config
from tts_bot.kiro_tmux_backend import KiroTmuxBackend

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DATA_DIR = os.getenv("DATA_DIR", os.path.expanduser("~/data/tts-tg-bot"))
API_URL = f"http://localhost:{os.getenv('API_PORT', '15001')}"
MAX_RETRIES = 3
RETRY_DELAY = 2
POLL_INTERVAL = 2

tmux = KiroTmuxBackend()
sent_hashes: set[str] = set()


def get_active_chat_id() -> int:
    try:
        return int(open(os.path.join(DATA_DIR, "active_chat_id")).read().strip())
    except Exception:
        return 0


def snapshot(win_id: str) -> str:
    return tmux.capture_pane(win_id, max_rows=80)


def extract_new_reply(old: str, new: str) -> str:
    """提取最新的 kiro-cli 回复"""
    new_lines = [l for l in new.strip().split("\n") if l.strip()]

    # 找最后一个回复块的起始位置
    last_reply = -1
    for i, line in enumerate(new_lines):
        s = line.strip()
        # 排除 kiro-cli 提示符和工具输出
        if s.startswith("> What would you like to do next"):
            continue
        if s.startswith("I will run the following command:"):
            continue
        if s.startswith("Purpose:"):
            continue
        if "(using tool:" in s:
            continue
        if s.startswith("- Completed in"):
            continue
        if s.startswith("> ") or s.startswith("[小K]") or s.startswith("[Kimi]"):
            last_reply = i

    if last_reply < 0:
        return ""

    reply_lines = []
    for line in new_lines[last_reply:]:
        s = line.strip()
        if s.startswith("λ >") or s.startswith("▸ Credits:") or s.startswith("> What would you like to do next?"):
            break
        if s.startswith("I will run the following command:") or s.startswith("Purpose:") or "(using tool:" in s:
            break
        if s.startswith("> "):
            reply_lines.append(s[2:])
        elif s.startswith("[小K]") or s.startswith("[Kimi]"):
            reply_lines.append(s)
        else:
            reply_lines.append(line.rstrip())

    if not reply_lines:
        return ""

    reply = "\n".join(reply_lines).strip()
    if not reply:
        return ""

    # hash 去重：只用回复前50字符做 hash，避免长回复截断导致不同 hash
    reply_hash = hashlib.md5(reply[:200].encode()).hexdigest()
    if reply_hash in sent_hashes:
        return ""
    sent_hashes.add(reply_hash)
    if len(sent_hashes) > 200:
        # 只清理一半，保留最近的
        sent_hashes.clear()

    return reply


def is_idle(content: str) -> bool:
    for line in reversed(content.strip().split("\n")):
        s = line.strip()
        if not s:
            continue
        return s.startswith("λ >") or s.startswith("> What would you like to do next?")
    return False


def content_changed(old: str, new: str) -> bool:
    old_clean = [l for l in old.strip().split("\n") if l.strip()]
    new_clean = [l for l in new.strip().split("\n") if l.strip()]
    return old_clean != new_clean


async def send_reply_with_retry(api_url: str, chat_id: int, text: str, bot_name: str = ""):
    """高并发重试发送"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                async with session.post(f"{api_url}/reply", json={
                    "message_id": "",
                    "reply": text,
                    "chat_id": chat_id,
                    "bot_name": bot_name,
                }) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        logger.info(f"回复已发送: {result}")
                        return True
                    logger.warning(f"发送失败 (HTTP {resp.status}), 重试 {attempt}/{MAX_RETRIES}")
        except Exception as e:
            logger.warning(f"发送异常: {e}, 重试 {attempt}/{MAX_RETRIES}")
        if attempt < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAY * attempt)

    logger.error(f"发送失败，已重试 {MAX_RETRIES} 次: {text[:80]}...")
    return False


def poll_session(sess: dict, state: dict) -> dict | None:
    """在线程中捕获单个 session（阻塞操作）"""
    name = sess["name"]
    win_id = sess["win_id"]

    try:
        current = snapshot(win_id)
    except Exception as e:
        logger.error(f"[{name}] 捕获失败: {e}")
        return None

    if not content_changed(state.get("last", ""), current):
        return None

    idle = is_idle(current)

    result = {
        "name": name,
        "win_id": win_id,
        "current": current,
        "idle": idle,
        "was_busy": state.get("was_busy", False),
        "sess": sess,
    }
    return result


async def main():
    from tts_bot.session_map import session_map

    def load_sessions():
        mapping = session_map.get_all()
        sessions = []
        for win_id, info in mapping.items():
            sessions.append({
                "name": info["bot_name"],
                "win_id": win_id,
                "api_url": info["api_url"],
                "chat_id": info.get("chat_id", 0),
            })
        if not sessions:
            sessions.append({
                "name": "kiro",
                "win_id": config.win_id,
                "api_url": API_URL,
                "chat_id": 0,
            })
        return sessions

    SESSIONS = load_sessions()
    # 每个 session 的状态
    states: dict[str, dict] = {}
    for sess in SESSIONS:
        states[sess["name"]] = {
            "last": snapshot(sess["win_id"]),
            "busy_start": "",  # busy 开始时的快照
            "was_busy": False,
        }

    print("=" * 50)
    print("🔄 多会话回复捕获器 (多线程 + 重试)")
    for sess in SESSIONS:
        print(f"🎯 {sess['name']}: {sess['win_id']} → {sess['api_url']}")
    print("=" * 50)

    executor = ThreadPoolExecutor(max_workers=max(len(SESSIONS), 4))
    loop = asyncio.get_event_loop()
    reload_counter = 0

    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL)

            # 每 60 秒重新加载 session 映射
            reload_counter += 1
            if reload_counter >= 30:
                reload_counter = 0
                new_sessions = load_sessions()
                new_names = {s["name"] for s in new_sessions}
                old_names = {s["name"] for s in SESSIONS}
                if new_names != old_names:
                    logger.info(f"Session 映射更新: {new_names}")
                    SESSIONS = new_sessions
                    for sess in SESSIONS:
                        if sess["name"] not in states:
                            states[sess["name"]] = {
                                "last": snapshot(sess["win_id"]),
                                "was_busy": False,
                            }

            # 多线程并发捕获所有 session
            futures = [
                loop.run_in_executor(executor, poll_session, sess, states[sess["name"]])
                for sess in SESSIONS
            ]
            results = await asyncio.gather(*futures)

            # 异步并发处理结果
            reply_tasks = []
            for r in results:
                if r is None:
                    continue

                name = r["name"]
                logger.info(f"[{name}] 内容变化, 空闲: {r['idle']}, was_busy: {r['was_busy']}")

                if not r["idle"]:
                    # 自动授权
                    last_lines = "\n".join(r["current"].strip().split("\n")[-3:])
                    if "[y/n/t]" in last_lines:
                        tmux.send_keys("t", r["win_id"])
                        logger.info(f"[{name}] 自动发送 t 授权")
                    if not states[name]["was_busy"]:
                        states[name]["busy_start"] = states[name]["last"]
                    states[name]["was_busy"] = True
                    states[name]["last"] = r["current"]
                    continue

                if r["was_busy"]:
                    reply = extract_new_reply(states[name]["busy_start"], r["current"])
                    if reply:
                        chat_id = r["sess"].get("chat_id") or get_active_chat_id()
                        api_url = r["sess"].get("api_url", API_URL)
                        bot_name = r["sess"].get("name", "kiro")
                        if chat_id:
                            logger.info(f"[{name}] 回复: {reply[:80]}...")
                            reply_tasks.append(send_reply_with_retry(api_url, chat_id, reply, bot_name))
                        else:
                            logger.warning(f"[{name}] 无 active_chat_id")
                    else:
                        logger.info(f"[{name}] 未提取到回复")
                    states[name]["was_busy"] = False

                states[name]["last"] = r["current"]

            # 并发发送所有回复
            if reply_tasks:
                await asyncio.gather(*reply_tasks)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"错误: {e}")
            await asyncio.sleep(5)

    executor.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
