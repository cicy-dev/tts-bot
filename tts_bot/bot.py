#!/usr/bin/env python3
"""
Telegram TTS Bot - 文字转语音机器人
支持双队列、ACK 机制、t1mux 管理命令
"""

import os
import sys
import argparse
import logging
import json
import time
import asyncio
import subprocess
from pathlib import Path
from typing import Optional

import edge_tts
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from .config import config
from .tmux_backend import TmuxBackend
from .kiro_tmux_backend import KiroTmuxBackend
from .stt_backend import STTBackend
from .default_stt import DefaultSTTBackend

# 配置日志
logger = logging.getLogger(__name__)

# 配置路径
DATA_DIR = os.getenv("DATA_DIR", os.path.expanduser("~/data/tts-tg-bot"))
LOG_DIR = os.path.join(DATA_DIR, "logs")
QUEUE_DIR = os.path.join(DATA_DIR, "queue")

# 确保目录存在
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(QUEUE_DIR, exist_ok=True)

# Bot Token（优先环境变量）
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    token_file = os.path.join(DATA_DIR, "token.txt")
    if os.path.exists(token_file):
        TOKEN = open(token_file).read().strip()
if not TOKEN:
    raise ValueError("BOT_TOKEN not found! Set BOT_TOKEN env or create token.txt")

# 支持的语音列表
VOICES = {
    "中文女声": "zh-CN-XiaoxiaoNeural",
    "中文男声": "zh-CN-YunxiNeural",
    "英文女声": "en-US-JennyNeural",
    "英文男声": "en-US-GuyNeural",
}

# 用户语音设置（默认中文女声）
user_voices = {}

# 全局实例
tmux_backend: Optional[TmuxBackend] = None
stt_backend: Optional[STTBackend] = None


def get_tmux_backend() -> TmuxBackend:
    """获取 tmux 后端"""
    global tmux_backend
    if tmux_backend is None:
        tmux_backend = KiroTmuxBackend()
    return tmux_backend


def get_stt_backend() -> STTBackend:
    """获取 STT 后端"""
    global stt_backend
    if stt_backend is None:
        stt_backend = DefaultSTTBackend()
    return stt_backend


async def text_to_speech(text: str, output_file: str, voice: str):
    """使用 edge-tts 转换文字为语音"""
    logger.debug(
        f"TTS 转换开始: text='{text[:50]}...', voice={voice}, output={output_file}"
    )
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)
    logger.debug(
        f"TTS 转换完成: {output_file}, 文件大小={os.path.getsize(output_file)} bytes"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    logger.info(f"用户启动 bot: user_id={user_id}, username=@{username}")

    user_voices[user_id] = VOICES["中文女声"]
    logger.debug(f"设置默认语音: user_id={user_id}, voice={VOICES['中文女声']}")

    help_text = """👋 你好！我是 W3C TTS Bot

📝 发送文字 → 我会转换成语音
🎙️ 发送语音 → 我会转换成文字

━━━━━━━━━━━━━━━━━━━━
📋 可用命令
━━━━━━━━━━━━━━━━━━━━
🎙️ 语音相关
  /voice - 查看和切换语音

⌨️ tmux 控制
  /tree - 显示 tmux 结构
  /capture - 捕获 tmux 内容
  /left /right /up /down - 发送方向键
  /resize_pane <高度> - 设置窗格高度

⚙️ 配置管理
  /win_id - 查看当前 win_id
  /win_id_set <id> - 设置 win_id
  /pane_height - 查看窗格高度
  /cut_max_rows - 查看截取行数
  /cut_rows_set <行数> - 设置截取行数

🪟 窗口管理
  /new_win <session> <window> [command] - 创建新窗口
  /del_win <win_id> - 删除窗口

当前 win_id: """

    await update.message.reply_text(help_text + f"```{config.win_id}```")


async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /voice 命令"""
    user_id = update.effective_user.id
    logger.debug(f"语音切换命令: user_id={user_id}, args={context.args}")

    if context.args:
        voice_name = " ".join(context.args)
        if voice_name in VOICES:
            user_voices[user_id] = VOICES[voice_name]
            logger.info(
                f"用户切换语音: user_id={user_id}, voice={voice_name} ({VOICES[voice_name]})"
            )
            await update.message.reply_text(f"✅ 已切换到：{voice_name}")
        else:
            logger.warning(f"无效语音选择: user_id={user_id}, voice={voice_name}")
            await update.message.reply_text(
                f"❌ 未知语音：{voice_name}\n\n"
                f"可用语音：\n" + "\n".join([f"- {v}" for v in VOICES.keys()])
            )
    else:
        current = [
            k
            for k, v in VOICES.items()
            if v == user_voices.get(user_id, VOICES["中文女声"])
        ][0]
        logger.debug(f"查询当前语音: user_id={user_id}, current={current}")
        await update.message.reply_text(
            f"🎙️ 当前语音：{current}\n\n"
            f"可用语音：\n"
            + "\n".join([f"- {v}" for v in VOICES.keys()])
            + f"\n\n使用方法：/voice 中文男声"
        )


def create_a_queue_file(
    text: str, user_id: int, chat_id: int, message_id: int, is_text: bool = False
) -> str:
    """创建 A 队列文件"""
    timestamp = int(time.time())
    queue_file = os.path.join(QUEUE_DIR, f"msg_{timestamp}_{message_id}_A.json")

    data = {
        "timestamp": timestamp,
        "message_id": message_id,
        "chat_id": chat_id,
        "user_id": user_id,
        "text": text,
        "is_text": is_text,
        "status": "pending",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open(queue_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    return queue_file


async def update_a_queue_status(
    queue_file: str, status: str, ack_message_id: int = None
):
    """更新 A 队列状态"""
    try:
        with open(queue_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["status"] = status
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if ack_message_id:
            data["ack_message_id"] = ack_message_id

        with open(queue_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"更新队列状态失败: {e}")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理文字消息"""
    text = update.message.text
    user_id = update.effective_user.id

    if not text:
        return

    # 检查是否为 t/n/y 决策字符
    if len(text) == 1 and config.is_tny_char(text):
        logger.info(f"收到 t/n/y 决策: user_id={user_id}, char={text}")
        tmux = get_tmux_backend()
        success = tmux.send_keys(text, config.win_id)
        if success:
            await update.message.reply_text(f"✅ 已发送: {text}")
        else:
            await update.message.reply_text(f"❌ 发送失败")
        return

    # 检查是否为特殊命令
    if text.startswith("/"):
        await handle_special_command(update, context, text)
        return

    logger.info(f"收到文字消息: user_id={user_id}, text='{text[:100]}...'")

    # 获取用户语音设置
    voice = user_voices.get(user_id, VOICES["中文女声"])
    logger.debug(f"使用语音: {voice}")

    # 发送处理中提示
    msg = await update.message.reply_text("⚙️ 处理中...")

    try:
        # 生成语音文件
        output_file = f"/tmp/tts_{update.message.message_id}.mp3"
        logger.debug(f"生成语音文件: {output_file}")
        await text_to_speech(text, output_file, voice)

        # 发送语音
        logger.debug(f"发送语音消息: file_size={os.path.getsize(output_file)} bytes")
        with open(output_file, "rb") as audio:
            await update.message.reply_voice(audio)

        # 删除临时文件
        os.remove(output_file)
        logger.debug(f"临时文件已删除: {output_file}")

        # 删除处理中提示
        await msg.delete()
        logger.info(
            f"TTS 处理成功: user_id={user_id}, message_id={update.message.message_id}"
        )

    except Exception as e:
        logger.error(f"TTS 处理失败: user_id={user_id}, error={e}", exc_info=True)
        await msg.edit_text(f"❌ 生成失败: {str(e)}")


async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理所有命令 (tree, capture, etc.)"""
    if not update.message or not update.message.text:
        return

    text = update.message.text
    user_id = update.effective_user.id

    # 如果是 /start 或 /voice，由各自的 handler 处理
    if text.startswith("/start") or text.startswith("/voice"):
        return

    logger.info(f"收到命令: user_id={user_id}, cmd={text}")
    await handle_special_command(update, context, text)


async def handle_special_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    """处理特殊命令"""
    user_id = update.effective_user.id
    logger.info(f"收到特殊命令: user_id={user_id}, cmd={text}")

    tmux = get_tmux_backend()
    parts = text.split()
    cmd = parts[0][1:].lower()
    args = parts[1:] if len(parts) > 1 else []

    try:
        if cmd == "left":
            success = tmux.send_keys("LEFT", config.win_id)
            await update.message.reply_text(
                f"✅ 已发送左箭头" if success else "❌ 发送失败"
            )

        elif cmd == "right":
            success = tmux.send_keys("RIGHT", config.win_id)
            await update.message.reply_text(
                f"✅ 已发送右箭头" if success else "❌ 发送失败"
            )

        elif cmd == "up":
            success = tmux.send_keys("UP", config.win_id)
            await update.message.reply_text(
                f"✅ 已发送上箭头" if success else "❌ 发送失败"
            )

        elif cmd == "down":
            success = tmux.send_keys("DOWN", config.win_id)
            await update.message.reply_text(
                f"✅ 已发送下箭头" if success else "❌ 发送失败"
            )

        elif cmd == "capture":
            content = tmux.capture_pane(config.win_id, max_rows=30)
            escaped = content.replace("`", "\\`")
            await update.message.reply_text(f"```{escaped}```")

        elif cmd == "tree":
            tree = tmux.tree_sessions()
            escaped = tree.replace("`", "\\`")
            await update.message.reply_text(f"```\n{escaped}\n```")

        elif cmd == "resize_pane":
            if len(args) < 1:
                await update.message.reply_text("❌ 请指定高度，例如: /resize_pane 100")
            else:
                height = int(args[0])
                success = tmux.resize_pane(config.win_id, height)
                await update.message.reply_text(
                    f"✅ 窗格高度已设置为 {height}" if success else "❌ 设置失败"
                )

        elif cmd == "win_id":
            escaped = config.win_id.replace("`", "\\`")
            await update.message.reply_text(f"当前 win_id: ```{escaped}```")

        elif cmd == "win_id_set":
            if len(args) < 1:
                await update.message.reply_text(
                    "❌ 请指定 win_id，例如: /win_id_set 6:master.0"
                )
            else:
                new_win_id = args[0]
                config.set_win_id(new_win_id)
                await update.message.reply_text(
                    f"✅ win_id 已设置为: ```{new_win_id}```"
                )

        elif cmd == "pane_height":
            height = tmux.get_pane_height(config.win_id)
            await update.message.reply_text(f"当前窗格高度: ```{height}```")

        elif cmd == "cut_max_rows":
            max_rows = config.capture_max_rows
            await update.message.reply_text(f"最大截取行数: ```{max_rows}```")

        elif cmd == "cut_rows_set":
            if len(args) < 1:
                await update.message.reply_text(
                    "❌ 请指定行数，例如: /cut_rows_set 100"
                )
            else:
                rows = int(args[0])
                config.set_cut_max_rows(rows)
                await update.message.reply_text(
                    f"✅ 最大截取行数已设置为: ```{rows}```"
                )

        elif cmd == "new_win":
            if len(args) < 2:
                await update.message.reply_text(
                    "❌ 用法: /new_win <session> <window> [command]"
                )
            else:
                session = args[0]
                window = args[1]
                command = args[2] if len(args) > 2 else config.init_code
                success = tmux.new_window(session, window, command, config.win_id)
                if success:
                    new_win_id = f"{session}:{window}.0"
                    config.set_win_id(new_win_id)
                    await update.message.reply_text(
                        f"✅ 已创建窗口: ```{new_win_id}```\n执行命令: {command}"
                    )
                else:
                    await update.message.reply_text("❌ 创建失败")

        elif cmd == "del_win":
            if len(args) < 1:
                await update.message.reply_text(
                    "❌ 请指定 win_id，例如: /del_win 6:master.0"
                )
            else:
                win_id = args[0]
                success = tmux.del_window(win_id)
                if success:
                    await update.message.reply_text(f"✅ 已删除窗口: {win_id}")
                else:
                    await update.message.reply_text(f"❌ 删除失败: {win_id}")

        else:
            await update.message.reply_text(f"❌ 未知命令: /{cmd}")

    except Exception as e:
        logger.error(f"处理命令失败: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 处理失败: {str(e)}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理语音消息"""
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    message_id = update.message.message_id

    logger.info(
        f"收到语音消息: user_id={user_id}, duration={update.message.voice.duration}s"
    )

    # 创建 A 队列文件（识别前）
    queue_file = create_a_queue_file(
        text="", user_id=user_id, chat_id=chat_id, message_id=message_id, is_text=False
    )
    logger.debug(f"创建 A 队列文件: {queue_file}")

    # 发送 ACK 消息
    ack_msg = await update.message.reply_text("🎧 识别中...")

    # 更新队列中的 ack_message_id
    await update_a_queue_status(queue_file, "pending", int(ack_msg.message_id))

    try:
        # 下载语音文件
        voice_file = await update.message.voice.get_file()
        file_path = f"/tmp/voice_{message_id}.ogg"
        await voice_file.download_to_drive(file_path)
        logger.debug(f"下载语音文件: {file_path}")

        # 调用 STT 识别
        stt = get_stt_backend()
        text = await stt.recognize(file_path)
        os.remove(file_path)

        if not text:
            await ack_msg.edit_text("❌ 识别失败")
            await update_a_queue_status(queue_file, "error")
            return

        logger.info(f"语音识别成功: text='{text}'")

        # 更新队列，填入识别结果
        with open(queue_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["text"] = text
        data["status"] = "ready"
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(queue_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        # 编辑 ACK 消息为处理中
        await ack_msg.edit_text("⚙️ 处理中...")

    except Exception as e:
        logger.error(f"语音处理失败: {e}", exc_info=True)
        await ack_msg.edit_text("❌ 识别失败")
        await update_a_queue_status(queue_file, "error")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮回调"""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("delete_"):
        try:
            await query.message.delete()
        except Exception as e:
            logger.error(f"删除消息失败: {e}")

    elif query.data.startswith("detail_"):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://localhost:15001/callback/{query.data}"
                ) as resp:
                    result = await resp.json()
                    full_text = result["text"]
            await query.message.reply_text(full_text)
        except Exception as e:
            logger.error(f"获取详情失败: {e}")


def main():
    """启动 bot"""
    parser = argparse.ArgumentParser(
        description="W3C TTS Bot - Telegram 文字转语音机器人"
    )
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format))

    file_handler = logging.FileHandler(
        os.path.join(LOG_DIR, "bot.log"), encoding="utf-8"
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(log_format))

    error_handler = logging.FileHandler(
        os.path.join(LOG_DIR, "error.log"), encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(log_format))

    logging.basicConfig(
        level=log_level, handlers=[console_handler, file_handler, error_handler]
    )

    logger.info("=" * 60)
    logger.info("🤖 Starting W3C TTS Bot...")
    logger.info(f"📝 Bot Username: @w3c_tts_bot")
    logger.info(f"🎙️ 支持语音: {', '.join(VOICES.keys())}")
    logger.info(f"🔧 当前 win_id: {config.win_id}")
    logger.info(f"🔧 最大截取行数: {config.capture_max_rows}")
    logger.info(f"🔧 调试模式: {'开启' if args.debug else '关闭'}")
    logger.info(f"📁 数据目录: {DATA_DIR}")
    logger.info(f"📁 日志目录: {LOG_DIR}")
    logger.info(f"📁 队列目录: {QUEUE_DIR}")
    logger.info("=" * 60)

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("voice", voice_command))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )
    app.add_handler(
        CommandHandler(
            [
                "tree",
                "capture",
                "left",
                "right",
                "up",
                "down",
                "resize_pane",
                "win_id",
                "win_id_set",
                "pane_height",
                "cut_max_rows",
                "cut_rows_set",
                "new_win",
                "del_win",
            ],
            handle_command,
        )
    )
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("✅ Bot is running!")
    logger.info("按 Ctrl+C 停止 bot")

    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭 bot...")
    except Exception as e:
        logger.error(f"Bot 运行错误: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
