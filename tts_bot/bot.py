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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
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

    bot_name = os.getenv("BOT_NAME", "kiro-bot")
    router_token = os.getenv("ROUTER_TOKEN", "")
    terminal_url = f"https://g-12345.cicy.de5.net/{bot_name}/?token={router_token}"

    # 欢迎消息
    welcome_text = """👋 欢迎使用 bot！

💬 你可以直接发送消息与我对话
⌨️ 使用下方键盘快速导航
"""
    
    # Reply keyboard with admin button
    reply_kb = ReplyKeyboardMarkup(
        [["/admin"]],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    
    await update.message.reply_text(welcome_text, reply_markup=reply_kb)


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


async def keys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /keys 命令 - 显示主要按键 inline keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("⬆️", callback_data="key_up"),
            InlineKeyboardButton("⬇️", callback_data="key_down"),
            InlineKeyboardButton("⬅️", callback_data="key_left"),
            InlineKeyboardButton("➡️", callback_data="key_right"),
        ],
        [
            InlineKeyboardButton("✅ yes", callback_data="key_yes"),
            InlineKeyboardButton("❌ no", callback_data="key_no"),
            InlineKeyboardButton("🔓 trust", callback_data="key_trust"),
        ],
        [
            InlineKeyboardButton("⏎ enter", callback_data="key_enter"),
            InlineKeyboardButton("⎋ esc", callback_data="key_esc"),
            InlineKeyboardButton("⛔ ctrl+c", callback_data="key_ctrlc"),
        ],
        [
            InlineKeyboardButton("📋 capture", callback_data="key_capture"),
        ],
        [
            InlineKeyboardButton("❌ 取消", callback_data="cancel_keys"),
        ],
    ]
    await update.message.reply_text(
        "⌨️ 快捷键盘\n" + "─" * 30,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def ttyd_token_refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /ttyd_token_refresh 命令 - 刷新所有 ttyd token（仅 owner）"""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ 无权限")
        return
    
    await update.message.reply_text("🔄 正在刷新所有 ttyd token...")
    
    # 触发 supervisor 重新加载配置
    try:
        import pymysql
        mysql_pass = os.getenv("MYSQL_PASSWORD", "")
        conn = pymysql.connect(host='localhost', user='root', password=mysql_pass, database='tts_bot')
        c = conn.cursor()
        # 修改一个字段触发 hash 变化
        c.execute("UPDATE bot_config SET status='active' WHERE status='active'")
        conn.commit()
        c.close()
        conn.close()
        
        await update.message.reply_text("✅ 已触发刷新，请等待 10 秒后重新打开 /admin 查看新链接")
    except Exception as e:
        await update.message.reply_text(f"❌ 刷新失败: {e}")



async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /admin 命令 - 显示所有管理工具（仅 owner）"""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ 无权限")
        return
    
    # 获取当前 bot 的 ttyd 端口
    ttyd_port = None
    try:
        import pymysql
        mysql_pass = os.getenv("MYSQL_PASSWORD", "")
        conn = pymysql.connect(host='localhost', user='root', password=mysql_pass, database='tts_bot')
        c = conn.cursor()
        c.execute("SELECT ttyd_port FROM bot_config WHERE bot_name=%s", (bot_name,))
        row = c.fetchone()
        if row:
            ttyd_port = row[0]
        c.close()
        conn.close()
    except Exception as e:
        logger.error(f"获取 ttyd 端口失败: {e}")
    
    keyboard = [
        [InlineKeyboardButton("🗄️ phpMyAdmin", url="https://g-12222.cicy.de5.net")],
    ]
    
    # 添加当前 bot 的 ttyd 链接（通过 cloudflare tunnel）
    if ttyd_port:
        keyboard.append([InlineKeyboardButton("🖥️ Terminal", url=f"https://g-{ttyd_port}.cicy.de5.net")])
    
    keyboard.extend([
        [InlineKeyboardButton("🖥️ VNC1", url="https://g-6080.cicy.de5.net"), 
         InlineKeyboardButton("🖥️ VNC2", url="https://g-6082.cicy.de5.net")],
        [InlineKeyboardButton("💻 Code Web", url="https://g-8080.cicy.de5.net")],
        [InlineKeyboardButton("📊 1Panel", url="https://g-16789.cicy.de5.net"), 
         InlineKeyboardButton("🚨 1Panel急", url="http://35.241.96.74:16789/7ae664ac51")],
        [InlineKeyboardButton("🔗 Linker", url="https://one.dash.cloudflare.com/73595dcb392b333ce6be9c923cc30930/networks/connectors/cloudflare-tunnels/cfd_tunnel/b948abd4-c804-4f96-b145-182f96bc085e/edit?tab=publicHostname")],
        [InlineKeyboardButton("❌ 取消", callback_data="cancel_admin")],
    ])
    
    await update.message.reply_text(
        "🛠️ 管理工具面板\n" + "─" * 30,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理文字消息 - 直接发送到 tmux，不检查 thinking"""
    text = update.message.text
    user_id = update.effective_user.id

    if not text:
        return

    # /tts on|off 控制
    if text.strip().lower() in ("/tts on", "/tts off"):
        val = "1" if "on" in text.lower() else "0"
        from tts_bot.session_map import session_map
        session_map.set_var("tts_enabled", val)
        await update.message.reply_text(f"TTS {'✅ 开启' if val == '1' else '❌ 关闭'}")
        return

    # 键盘按钮映射
    KB_MAP = {
        "⬆️": "/up", "⬇️": "/down", "⬅️": "/left", "➡️": "/right",
        "✅ yes": "/yes", "❌ no": "/no", "🔓 trust": "/trust",
        "⎋ esc": "/esc", "⏎ enter": "/enter", "⛔ ctrl+c": "/ctrlc",
        "📋 capture": "/capture",
    }
    if text in KB_MAP:
        text = KB_MAP[text]

    # 检查是否为 t/n/y 决策字符
    if len(text) == 1 and config.is_tny_char(text):
        logger.info(f"收到 t/n/y 决策: user_id={user_id}, char={text}")
        tmux = get_tmux_backend()
        tmux.send_msg(text, win_id)
        return

    # 检查是否为特殊命令
    if text.startswith("/"):
        await handle_special_command(update, context, text)
        return

    logger.info(f"收到文字消息: user_id={user_id}, text='{text[:100]}...'")

    # 直接发送到 tmux（像真人打字一样）
    tmux = get_tmux_backend()
    tmux.send_msg(text, win_id)
    logger.info(f"已发送到 tmux: {bot_name} → {win_id}")

    # 记录 Q&A pair 到 MySQL（question 部分）
    try:
        import pymysql as _pymysql
        _conn = _pymysql.connect(
            host='localhost', user='root',
            password=os.getenv("MYSQL_PASSWORD", ""),
            database='tts_bot', charset='utf8mb4', autocommit=True
        )
        _c = _conn.cursor()
        _c.execute("""
            INSERT INTO qa_pair (bot_name, chat_id, question, status)
            VALUES (%s, %s, %s, 'pending')
        """, (bot_name, update.message.chat_id, text))
        _c.close()
        _conn.close()
    except Exception as e:
        logger.warning(f"记录 QA pair 失败: {e}")

    # 更新 session_map 中的 chat_id
    from tts_bot.session_map import session_map
    session_map.update_chat_id(win_id, update.message.chat_id)


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
            tmux.send_keys("LEFT", win_id)

        elif cmd == "right":
            tmux.send_keys("RIGHT", win_id)

        elif cmd == "up":
            tmux.send_keys("UP", win_id)

        elif cmd == "down":
            tmux.send_keys("DOWN", win_id)

        elif cmd == "capture":
            content = tmux.capture_pane(win_id, max_rows=30)
            await update.message.reply_text(f"<pre>{content}</pre>", parse_mode='HTML')

        elif cmd == "tre":
            tree = tmux.tree_sessions()
            await update.message.reply_text(f"<pre>{tree}</pre>", parse_mode='HTML')

        elif cmd == "map":
            from tts_bot.session_map import session_map
            mapping = session_map.get_all()
            lines = ["🗺️ <b>Session Map</b>\n"]
            # 加上master（小K自己）
            lines.append("👑 <b>master</b>")
            lines.append("  ├ master:cicy_master_xk_bot → 小K")
            groups = {}
            for wid, info in mapping.items():
                g = info.get("group", "unknown")
                groups.setdefault(g, []).append((wid, info["bot_name"]))
            for g in sorted(groups.keys()):
                lines.append(f"\n📁 <b>{g}</b>")
                for wid, name in groups[g]:
                    lines.append(f"  ├ {wid} → {name}")
            await update.message.reply_text("\n".join(lines), parse_mode='HTML')

        elif cmd == "esc":
            tmux.send_keys("Escape", win_id)

        elif cmd == "enter":
            tmux.send_keys("Enter", win_id)

        elif cmd == "ctrlc":
            tmux.send_keys("C-c", win_id)

        elif cmd == "trust":
            tmux.send_keys("t", win_id)

        elif cmd == "yes":
            tmux.send_keys("y", win_id)

        elif cmd == "no":
            tmux.send_keys("n", win_id)

        else:
            await update.message.reply_text(f"❌ 未知命令: /{cmd}", parse_mode='HTML')

    except Exception as e:
        logger.error(f"处理命令失败: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 处理失败: {str(e)}", parse_mode='HTML')


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理语音消息 - STT 识别后发送到 tmux"""
    user_id = update.effective_user.id
    message_id = update.message.message_id

    logger.info(
        f"收到语音消息: user_id={user_id}, duration={update.message.voice.duration}s"
    )

    # 发送 ACK 消息
    ack_msg = await update.message.reply_text("🎧 识别中...", reply_to_message_id=message_id, parse_mode='HTML')

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
            return

        logger.info(f"语音识别成功: text='{text}'")

        # 发送到 tmux，跟文字消息一样
        tmux = get_tmux_backend()
        tmux.send_msg(text, win_id)

        await ack_msg.edit_text(f"🎤 {text}", parse_mode='HTML')

        # 记录 QA pair
        try:
            import pymysql as _pymysql
            _conn = _pymysql.connect(
                host='localhost', user='root',
                password=os.getenv("MYSQL_PASSWORD", ""),
                database='tts_bot', charset='utf8mb4', autocommit=True
            )
            _c = _conn.cursor()
            _c.execute("""
                INSERT INTO qa_pair (bot_name, chat_id, question, status)
                VALUES (%s, %s, %s, 'pending')
            """, (bot_name, update.message.chat_id, text))
            _c.close()
            _conn.close()
        except Exception as e:
            logger.warning(f"记录 QA pair 失败: {e}")

        # 更新 session_map 中的 chat_id
        from tts_bot.session_map import session_map
        session_map.update_chat_id(win_id, update.message.chat_id)

    except Exception as e:
        logger.error(f"语音处理失败: {e}", exc_info=True)
        await ack_msg.edit_text("❌ 识别失败", parse_mode='HTML')


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮回调"""
    query = update.callback_query
    await query.answer()

    # 取消 admin 面板
    if query.data == "cancel_admin":
        await query.message.delete()
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id - 1
            )
        except:
            pass
        return
    
    # 取消 keys 面板
    if query.data == "cancel_keys":
        await query.message.delete()
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id - 1
            )
        except:
            pass
        return

    # 按键回调: key_{action}
    if query.data.startswith("key_"):
        action = query.data[4:]
        
        KEY_CMD_MAP = {
            "up": "/up", "down": "/down", "left": "/left", "right": "/right",
            "yes": "/yes", "no": "/no", "trust": "/trust",
            "enter": "/enter", "esc": "/esc", "ctrlc": "/ctrlc",
            "capture": "/capture",
        }
        
        cmd = KEY_CMD_MAP.get(action)
        if cmd:
            fake_update = update
            fake_update.message = query.message
            fake_update.effective_user = query.from_user
            
            await handle_special_command(fake_update, context, cmd)
            # 不修改消息，保持键盘可用
        return

    # 授权回调: auth_{y|n|t}_{win_id}
    if query.data.startswith("auth_"):
        parts = query.data.split("_", 2)  # auth, action, win_id
        if len(parts) == 3:
            action = parts[1]  # y / n / t
            win_id = parts[2]
            tmux = get_tmux_backend()
            tmux.send_msg(action, win_id)
            label = {"t": "✅ Trust", "y": "👍 Yes", "n": "❌ No"}.get(action, action)
            await query.edit_message_text(f"{label} → 已发送到 {win_id}", parse_mode='HTML')
            return

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
        # TODO: 未来迭代支持多人聊天，动态发送到多个 session
        tmux.send_msg(text, win_id)

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
    global win_id, bot_name, group, api_url  # 设置为全局变量供其他函数使用
    
    parser = argparse.ArgumentParser(
        description="W3C TTS Bot - Telegram 文字转语音机器人"
    )
    parser.add_argument("--bot-name", required=True, help="Bot 名称")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    args = parser.parse_args()
    
    bot_name = args.bot_name
    
    # 从 MySQL 读取所有配置
    import pymysql
    try:
        mysql_pass = os.getenv("MYSQL_PASSWORD", "")
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password=mysql_pass,
            database='tts_bot',
            charset='utf8mb4'
        )
        c = conn.cursor()
        c.execute("""
            SELECT bot_token, tmux_session, tmux_window, group_name, api_url
            FROM bot_config
            WHERE bot_name=%s AND status='active'
        """, (bot_name,))
        row = c.fetchone()
        c.close()
        conn.close()
        
        if not row:
            raise ValueError(f"Bot {bot_name} not found or disabled in MySQL")
        
        TOKEN = row[0]
        tmux_session = row[1] or "worker"
        tmux_window = row[2] or bot_name
        group = row[3] or "worker"
        api_url = row[4] or "http://localhost:15001"
        # 动态生成 win_id
        from tts_bot.session_map import format_win_id
        win_id = format_win_id(tmux_session, tmux_window)
    except Exception as e:
        raise ValueError(f"Failed to get config from MySQL: {e}")

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

    # 隐藏 httpx 日志中的 token
    logging.getLogger("httpx").setLevel(logging.WARNING)

    logger.info("=" * 60)
    logger.info("🤖 Starting W3C TTS Bot...")
    logger.info(f"📝 Bot Username: @w3c_tts_bot")
    logger.info(f"🎙️ 支持语音: {', '.join(VOICES.keys())}")
    logger.info(f"🔧 当前 win_id: {win_id}")
    logger.info(f"🔧 最大截取行数: {config.capture_max_rows}")
    logger.info(f"🔧 调试模式: {'开启' if args.debug else '关闭'}")
    logger.info(f"📁 数据目录: {DATA_DIR}")
    logger.info(f"📁 日志目录: {LOG_DIR}")
    logger.info(f"📁 队列目录: {QUEUE_DIR}")
    logger.info("=" * 60)

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("voice", voice_command))
    app.add_handler(CommandHandler("keys", keys_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("ttyd_token_refresh", ttyd_token_refresh_command))
    app.add_handler(CommandHandler("checklist", checklist_command))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )
    app.add_handler(
        CommandHandler(
            [
                "tre",
                "capture",
                "map",
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

    # 使用从 MySQL 读取的配置
    # win_id 作为局部变量使用

    # worker 工作目录: master用~/projects, 其他用~/workers/<bot_name>
    if bot_name == "cicy_master_xk_bot":
        work_dir = os.path.expanduser("~/projects")
    else:
        work_dir = os.path.expanduser(f"~/workers/{bot_name}")
    os.makedirs(work_dir, exist_ok=True)
    config.work_dir = work_dir

    # 注册到 session_map
    from tts_bot.session_map import session_map
    session_map.register(win_id, bot_name, api_url, bot_token=TOKEN, group=group)
    logger.info(f"📡 BOT_NAME={bot_name}, group={group}, win_id={win_id}, work_dir={work_dir}")

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

    # 设置 bot menu commands
    async def post_init(application):
        await application.bot.set_my_commands([
            ("start", "启动 / 菜单"),
            ("map", "Worker 地图"),
            ("voice", "切换语音"),
            ("capture", "截屏"),
            ("tre", "目录结构"),
            ("trust", "授权 Trust"),
            ("yes", "授权 Yes"),
            ("no", "授权 No"),
            ("ctrlc", "Ctrl+C"),
            ("esc", "ESC"),
            ("enter", "Enter"),
        ])
    app.post_init = post_init

    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭 bot...")
    except Exception as e:
        logger.error(f"Bot 运行错误: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
