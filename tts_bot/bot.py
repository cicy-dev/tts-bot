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

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from .config import config

OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
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
    """调用 TTS API(:15002) 转换文字为语音"""
    logger.debug(f"TTS 转换开始: text='{text[:50]}...', voice={voice}, output={output_file}")
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.post('http://localhost:15002/tts', json={"text": text, "voice": voice}) as resp:
            with open(output_file, 'wb') as f:
                f.write(await resp.read())
    logger.debug(f"TTS 转换完成: {output_file}, 文件大小={os.path.getsize(output_file)} bytes")


async def checklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /checklist 命令"""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ 无权限", parse_mode='HTML')
        return
    checklist_path = os.path.expanduser("~/personal/checklist.md")
    if os.path.exists(checklist_path):
        with open(checklist_path, "r") as f:
            content = f.read()
        # 截断避免超长
        if len(content) > 4000:
            content = content[:4000] + "\n..."
        await update.message.reply_text(content, parse_mode='HTML')
    else:
        await update.message.reply_text("📋 暂无清单", parse_mode='HTML')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    logger.info(f"用户启动 bot: user_id={user_id}, username=@{username}")

    user_voices[user_id] = VOICES["中文女声"]
    logger.debug(f"设置默认语音: user_id={user_id}, voice={VOICES['中文女声']}")

    help_text = """👋 你好！我是 W3C TTS Bot
_______________________________________________
⌨️ 方向键
           /up
/left  /down  /right

🔧 控制
/esc  /enter  /ctrlc

🤖 Kiro
/yes  /no  /trust - 授权 [y/n/t]

📋 工具
/voice  /tree  /capture
"""

    # 创建Mini App按钮
    keyboard = []
    tmux_session = os.getenv("TMUX_SESSION", "kiro_master")
    terminal_url = f"https://g-12345.cicy.de5.net/{tmux_session}/?token=pb200898"
    if user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("🖥️ 打开终端", web_app=WebAppInfo(url=terminal_url))])
        keyboard.append([InlineKeyboardButton("🖥️ VNC 桌面", url="https://g-6080.cicy.de5.net/"), InlineKeyboardButton("🖥️ VNC 桌面2", url="https://g-6082.cicy.de5.net/")])
        keyboard.append([InlineKeyboardButton("💻 Code Web", url="https://g-8080.cicy.de5.net/")])
        keyboard.append([InlineKeyboardButton("📊 1Panel", url="https://g-16789.cicy.de5.net"), InlineKeyboardButton("🚨 1Panel急", url="http://35.241.96.74:16789/7ae664ac51")])
        keyboard.append([InlineKeyboardButton("🔗 Linker", url="https://one.dash.cloudflare.com/73595dcb392b333ce6be9c923cc30930/networks/connectors/cloudflare-tunnels/cfd_tunnel/b948abd4-c804-4f96-b145-182f96bc085e/edit?tab=publicHostname")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        help_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )


async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /voice 命令 - inline keyboard 选择语音"""
    user_id = update.effective_user.id
    current_voice = user_voices.get(user_id, VOICES["中文女声"])
    current_name = next((k for k, v in VOICES.items() if v == current_voice), "中文女声")

    buttons = []
    for name in VOICES:
        label = f"✅ {name}" if name == current_name else name
        buttons.append([InlineKeyboardButton(label, callback_data=f"voice_{name}")])

    await update.message.reply_text(
        f"🎙️ 当前语音：{current_name}",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode='HTML'
    )


def create_a_queue_file(
    text: str, user_id: int, chat_id: int, message_id: int, is_text: bool = False
) -> str:
    """创建队列消息（Redis）"""
    from .redis_queue import rq
    import time as _time

    msg_id = f"msg_{int(_time.time())}_{message_id}"
    data = {
        "message_id": message_id,
        "chat_id": chat_id,
        "user_id": user_id,
        "text": text,
        "is_text": is_text,
    }
    rq.push(msg_id, data)
    return msg_id


async def update_a_queue_status(
    queue_id: str, status: str, ack_message_id: int = None
):
    """更新队列状态（Redis）"""
    from .redis_queue import rq

    data = rq.get(queue_id)
    if data:
        data["status"] = status
        if ack_message_id:
            data["ack_message_id"] = ack_message_id
        rq.update(queue_id, data)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理文字消息 - 直接发送到 tmux，不检查 thinking"""
    text = update.message.text
    user_id = update.effective_user.id

    if not text:
        return

    # 检查是否为 t/n/y 决策字符
    if len(text) == 1 and config.is_tny_char(text):
        logger.info(f"收到 t/n/y 决策: user_id={user_id}, char={text}")
        tmux = get_tmux_backend()
        tmux.send_keys(text, config.win_id)
        return

    # 检查是否为特殊命令
    if text.startswith("/"):
        await handle_special_command(update, context, text)
        return

    logger.info(f"收到文字消息: user_id={user_id}, text='{text[:100]}...'")

    # 发送到两个 tmux 会话
    tmux = get_tmux_backend()
    import asyncio as _asyncio
    
    # 1. 发送到 kimi（带延迟）
    tmux.send_text(text, "kimi:master")
    await _asyncio.sleep(1.0)
    tmux.send_keys("ENTER", "kimi:master")
    
    # 2. 发送到 kiro（我）
    tmux.send_text(text, config.win_id)
    await _asyncio.sleep(config.tmux_send_delay)
    tmux.send_keys("ENTER", config.win_id)

    # 记录活跃 chat_id，供回复捕获器使用
    chat_id_file = os.path.join(DATA_DIR, "active_chat_id")
    with open(chat_id_file, "w") as f:
        f.write(str(update.message.chat_id))

    # 发送状态消息，回复到达后自动删除
    ack_msg = await update.message.reply_text("💭 Thinking...", parse_mode='HTML')
    ack_file = os.path.join(DATA_DIR, "ack_message_id")
    with open(ack_file, "w") as f:
        f.write(str(ack_msg.message_id))


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
            tmux.send_keys("LEFT", config.win_id)

        elif cmd == "right":
            tmux.send_keys("RIGHT", config.win_id)

        elif cmd == "up":
            tmux.send_keys("UP", config.win_id)

        elif cmd == "down":
            tmux.send_keys("DOWN", config.win_id)

        elif cmd == "capture":
            content = tmux.capture_pane(config.win_id, max_rows=30)
            await update.message.reply_text(f"<pre>{content}</pre>", parse_mode='HTML')

        elif cmd == "tree":
            tree = tmux.tree_sessions()
            await update.message.reply_text(f"<pre>{tree}</pre>", parse_mode='HTML')

        elif cmd == "esc":
            tmux.send_keys("Escape", config.win_id)

        elif cmd == "enter":
            tmux.send_keys("Enter", config.win_id)

        elif cmd == "ctrlc":
            tmux.send_keys("C-c", config.win_id)

        elif cmd == "trust":
            tmux.send_keys("t", config.win_id)

        elif cmd == "yes":
            tmux.send_keys("y", config.win_id)

        elif cmd == "no":
            tmux.send_keys("n", config.win_id)

        else:
            await update.message.reply_text(f"❌ 未知命令: /{cmd}", parse_mode='HTML')

    except Exception as e:
        logger.error(f"处理命令失败: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 处理失败: {str(e)}", parse_mode='HTML')


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理语音消息"""
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    message_id = update.message.message_id

    logger.info(
        f"收到语音消息: user_id={user_id}, duration={update.message.voice.duration}s"
    )

    # 创建队列消息（识别前）
    queue_id = create_a_queue_file(
        text="", user_id=user_id, chat_id=chat_id, message_id=message_id, is_text=False
    )
    logger.debug(f"创建队列消息: {queue_id}")

    # 发送 ACK 消息（reply 到用户语音）
    ack_msg = await update.message.reply_text("🎧 识别中...", reply_to_message_id=message_id, parse_mode='HTML')

    # 更新队列中的 ack_message_id
    await update_a_queue_status(queue_id, "pending", int(ack_msg.message_id))

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
            await ack_msg.edit_text("❌ 识别失败", parse_mode='HTML')
            await update_a_queue_status(queue_id, "error")
            return

        logger.info(f"语音识别成功: text='{text}'")

        # 发送到 tmux，跟文字消息一样
        tmux = get_tmux_backend()
        tmux.send_text(text, config.win_id)
        import asyncio as _asyncio
        await _asyncio.sleep(config.tmux_send_delay)
        tmux.send_keys("ENTER", config.win_id)

        # 记录活跃 chat_id
        chat_id_file = os.path.join(DATA_DIR, "active_chat_id")
        with open(chat_id_file, "w") as f:
            f.write(str(update.message.chat_id))

        await ack_msg.edit_text(f"🎤 {text}", parse_mode='HTML')

        # 存 ack message_id，回复到达后删除
        ack_file = os.path.join(DATA_DIR, "ack_message_id")
        with open(ack_file, "w") as f:
            f.write(str(ack_msg.message_id))

    except Exception as e:
        logger.error(f"语音处理失败: {e}", exc_info=True)
        await ack_msg.edit_text("❌ 识别失败", parse_mode='HTML')
        await update_a_queue_status(queue_id, "error")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮回调"""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("voice_"):
        voice_name = query.data[6:]
        if voice_name in VOICES:
            user_voices[query.from_user.id] = VOICES[voice_name]
            buttons = []
            for name in VOICES:
                label = f"✅ {name}" if name == voice_name else name
                buttons.append([InlineKeyboardButton(label, callback_data=f"voice_{name}")])
            await query.edit_message_text(
                f"🎙️ 已切换到：{voice_name}",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode='HTML'
            )


async def ocr_image(file_path: str) -> str:
    """三层 OCR: Gemini → OCR.space → EasyOCR API"""
    import base64
    # 1. Gemini API
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        try:
            with open(file_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [
                    {"text": "提取图片中的所有文字，只返回文字内容，不要解释"},
                    {"inline_data": {"mime_type": "image/png", "data": img_data}}
                ]}]
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                        if text:
                            logger.info("OCR 使用 Gemini")
                            return text
                    else:
                        logger.warning(f"Gemini OCR {resp.status}, fallback")
        except Exception as e:
            logger.warning(f"Gemini OCR 失败: {e}, fallback")

    # 2. OCR.space
    try:
        data = aiohttp.FormData()
        data.add_field("apikey", "helloworld")
        data.add_field("language", "chs")
        data.add_field("filetype", "png")
        data.add_field("file", open(file_path, "rb"), filename="image.png")
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.ocr.space/parse/image", data=data) as resp:
                result = await resp.json()
        if result.get("ParsedResults"):
            text = result["ParsedResults"][0].get("ParsedText", "").strip()
            if text:
                logger.info("OCR 使用 OCR.space")
                return text
    except Exception as e:
        logger.warning(f"OCR.space 失败: {e}, fallback EasyOCR")

    # 3. EasyOCR API（独立容器 15010）
    try:
        data = aiohttp.FormData()
        data.add_field("file", open(file_path, "rb"), filename="image.png")
        async with aiohttp.ClientSession() as session:
            async with session.post("http://localhost:15010/ocr", data=data) as resp:
                result = await resp.json()
                text = result.get("text", "").strip()
                if text:
                    logger.info("OCR 使用 EasyOCR API")
                    return text
    except Exception as e:
        logger.error(f"EasyOCR API 也失败: {e}")

    return ""


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理图片消息 - OCR 识别后发送到 tmux"""
    user_id = update.effective_user.id
    message_id = update.message.message_id
    logger.info(f"收到图片消息: user_id={user_id}")

    ack_msg = await update.message.reply_text("🔍 识别中...", reply_to_message_id=message_id, parse_mode='HTML')

    try:
        # 下载图片（取最大尺寸）
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        file_path = f"/tmp/photo_{message_id}.png"
        await photo_file.download_to_drive(file_path)

        # OCR 识别
        text = await ocr_image(file_path)
        os.remove(file_path)

        if not text:
            await ack_msg.edit_text("❌ 未识别到文字", parse_mode='HTML')
            return

        logger.info(f"图片 OCR 成功: text='{text[:100]}'")

        # 发送到 tmux
        tmux = get_tmux_backend()
        import asyncio as _asyncio
        tmux.send_text(text, "kimi:master")
        await _asyncio.sleep(1.0)
        tmux.send_keys("ENTER", "kimi:master")
        tmux.send_text(text, config.win_id)
        await _asyncio.sleep(config.tmux_send_delay)
        tmux.send_keys("ENTER", config.win_id)

        # 记录活跃 chat_id
        chat_id_file = os.path.join(DATA_DIR, "active_chat_id")
        with open(chat_id_file, "w") as f:
            f.write(str(update.message.chat_id))

        await ack_msg.edit_text(f"📷 {text[:200]}", parse_mode='HTML')

        # 存 ack message_id
        ack_file = os.path.join(DATA_DIR, "ack_message_id")
        with open(ack_file, "w") as f:
            f.write(str(ack_msg.message_id))

    except Exception as e:
        logger.error(f"图片处理失败: {e}", exc_info=True)
        await ack_msg.edit_text("❌ 识别失败", parse_mode='HTML')

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
            await query.message.reply_text(full_text, parse_mode='HTML')
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
    app.add_handler(CommandHandler("checklist", checklist_command))
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
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("✅ Bot is running!")

    # 注册 session map
    from tts_bot.session_map import session_map
    bot_name = os.getenv("BOT_NAME", "kiro-bot")
    tmux_session = os.getenv("TMUX_SESSION", "")
    if tmux_session:
        win_id = f"{tmux_session}:0"
        config.set_win_id(win_id)
    api_port = os.getenv("API_PORT", "15001")
    api_url = f"http://localhost:{api_port}"
    session_map.register(config.win_id, bot_name, api_url, bot_token=TOKEN)
    logger.info(f"📡 BOT_NAME={bot_name}, win_id={config.win_id}")
    logger.info(f"📡 Session Map: {config.win_id} → {bot_name} ({api_url})")

    # 启动时检测外部服务
    import urllib.request
    for name, url in [("TTS", "http://localhost:15002/health"), ("STT", "http://localhost:15003/health"), ("Redis", "http://localhost:6379")]:
        try:
            if name == "Redis":
                import redis as _r
                _r.Redis(host='localhost', port=6379).ping()
            else:
                urllib.request.urlopen(url, timeout=3)
            logger.info(f"  ✅ {name} OK")
        except Exception:
            logger.warning(f"  ⚠️ {name} 不可用")
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
