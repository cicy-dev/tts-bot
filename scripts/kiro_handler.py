#!/usr/bin/env python3
"""
Kiro-CLI 消息处理器
双队列模式：A队列→tmux，B队列→用户
支持 Thinking 检测、t/n/y 决策、ACK 管理
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from tts_bot.config import config
from tts_bot.kiro_tmux_backend import KiroTmuxBackend

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 配置路径
DATA_DIR = os.path.expanduser("~/data/tts-tg-bot")
QUEUE_DIR = os.path.join(DATA_DIR, "queue")
os.makedirs(QUEUE_DIR, exist_ok=True)

# tmux 后端
tmux = KiroTmuxBackend()

# Bot Token
TOKEN_FILE = os.path.join(DATA_DIR, "token.txt")
BOT_TOKEN = open(TOKEN_FILE).read().strip()

# 已处理的文件
processed_a = set()
processed_b = set()


async def send_to_user(chat_id: int, text: str):
    """发送消息给用户"""
    try:
        from telegram import Bot

        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=chat_id, text=text)
        logger.info(f"已发送给用户: chat_id={chat_id}")
    except Exception as e:
        logger.error(f"发送消息失败: {e}")


def get_a_queue_files() -> list:
    """获取所有 A 队列文件"""
    try:
        files = sorted([f for f in os.listdir(QUEUE_DIR) if f.endswith("_A.json")])
        return files
    except Exception as e:
        logger.error(f"扫描 A 队列失败: {e}")
        return []


def get_b_queue_files() -> list:
    """获取所有 B 队列文件"""
    try:
        files = sorted(
            [f for f in os.listdir(QUEUE_DIR) if f.endswith("_B_reply.json")]
        )
        return files
    except Exception as e:
        logger.error(f"扫描 B 队列失败: {e}")
        return []


def is_thinking(win_id: str) -> bool:
    """检测 tmux 是否处于 Thinking 状态"""
    return tmux.check_thinking(win_id)


async def send_to_tmux(text: str, win_id: str) -> bool:
    """发送消息到 tmux"""
    try:
        # 发送文本
        tmux.send_text(text, win_id)
        logger.info(f"已发送文本到 tmux: {win_id}")

        # 等待后发送 ENTER
        await asyncio.sleep(config.tmux_send_delay)
        tmux.send_keys("ENTER", win_id)
        logger.info(f"已发送 ENTER 到 tmux: {win_id}")

        return True
    except Exception as e:
        logger.error(f"发送 tmux 失败: {e}")
        return False


async def process_a_queue(filename: str) -> bool:
    """处理 A 队列文件"""
    global processed_a

    filepath = os.path.join(QUEUE_DIR, filename)
    if filepath in processed_a:
        return True

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        status = data.get("status")
        if status != "ready":
            return False

        message_id = data.get("message_id")
        chat_id = data.get("chat_id")
        user_id = data.get("user_id")
        text = data.get("text", "")
        ack_msg_id = data.get("ack_message_id")

        logger.info(f"处理 A 队列: msg_{data.get('timestamp')}_{message_id}")
        logger.info(f"内容: {text[:100]}...")

        # 发送到 tmux
        success = await send_to_tmux(text, config.win_id)

        if success:
            # 更新状态
            data["status"] = "sent_to_tmux"
            data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

            processed_a.add(filepath)
            logger.info(f"A队列处理完成: {filename}")
            return True
        else:
            logger.error(f"发送 tmux 失败: {filename}")
            return False

    except Exception as e:
        logger.error(f"处理 A 队列失败: {e}")
        return False


async def process_b_queue(filename: str) -> bool:
    """处理 B 队列文件"""
    global processed_b

    filepath = os.path.join(QUEUE_DIR, filename)
    if filepath in processed_b:
        return True

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        status = data.get("status")
        if status != "ready":
            return False

        message_id = data.get("message_id")
        chat_id = data.get("chat_id")
        ack_msg_id = data.get("ack_message_id")
        reply = data.get("reply", "")

        logger.info(f"处理 B 队列: msg_{data.get('timestamp')}_{message_id}")
        logger.info(f"回复: {reply[:100]}...")

        # 删除 ACK 消息
        if ack_msg_id:
            try:
                from telegram import Bot

                bot = Bot(token=BOT_TOKEN)
                await bot.delete_message(chat_id=chat_id, message_id=ack_msg_id)
                logger.info(f"已删除 ACK 消息: {ack_msg_id}")
            except Exception as e:
                logger.warning(f"删除 ACK 消息失败: {e}")

        # 发送回复给用户
        if chat_id:
            await send_to_user(chat_id, reply)

        # 更新状态
        data["status"] = "sent_to_user"
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        processed_b.add(filepath)
        logger.info(f"B队列处理完成: {filename}")

        return True

    except Exception as e:
        logger.error(f"处理 B 队列失败: {e}")
        return False


def cleanup_processed_files():
    """清理已处理的文件"""
    global processed_a, processed_b

    for filepath in list(processed_a):
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("status") == "sent_to_user":
                    os.remove(filepath)
                    logger.info(f"已清理 A 队列: {filepath}")
                    processed_a.discard(filepath)
        except Exception as e:
            logger.warning(f"清理 A 队列失败: {e}")

    for filepath in list(processed_b):
        try:
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("status") == "sent_to_user":
                    os.remove(filepath)
                    logger.info(f"已清理 B 队列: {filepath}")
                    processed_b.discard(filepath)
        except Exception as e:
            logger.warning(f"清理 B 队列失败: {e}")


async def main():
    """主循环"""
    print("=" * 60)
    print("🤖 Kiro-CLI 消息处理器已启动（双队列模式）")
    print(f"📁 队列目录: {QUEUE_DIR}")
    print(f"🎯 当前 win_id: {config.win_id}")
    print(f"📏 最大截取行数: {config.capture_max_rows}")
    print("=" * 60)
    print()

    while True:
        try:
            # 获取 A 队列文件
            a_files = get_a_queue_files()
            if a_files:
                logger.info(f"发现 {len(a_files)} 个 A 队列文件")

                for filename in a_files:
                    filepath = os.path.join(QUEUE_DIR, filename)
                    if filepath not in processed_a:
                        await process_a_queue(filename)

            # 获取 B 队列文件
            b_files = get_b_queue_files()
            if b_files:
                logger.info(f"发现 {len(b_files)} 个 B 队列文件")

                for filename in b_files:
                    filepath = os.path.join(QUEUE_DIR, filename)
                    if filepath not in processed_b:
                        await process_b_queue(filename)

            # 清理已处理的文件
            cleanup_processed_files()

            # 等待
            await asyncio.sleep(2)

        except KeyboardInterrupt:
            print("\n👋 退出中...")
            break
        except Exception as e:
            logger.error(f"主循环错误: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 已退出")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)
