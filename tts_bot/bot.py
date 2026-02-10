#!/usr/bin/env python3
"""
Telegram TTS Bot - 文字转语音机器人
"""

import os
import sys
import argparse
import logging
import json
import time
import asyncio
import subprocess
import edge_tts
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# 配置日志
logger = logging.getLogger(__name__)

# 配置路径
DATA_DIR = os.path.expanduser("~/data/tts-tg-bot")
LOG_DIR = os.path.join(DATA_DIR, "logs")
QUEUE_DIR = os.path.join(DATA_DIR, "queue")

# 管理员 ID（接收转发消息）
ADMIN_ID = 7943234085  # 你的 user_id

# 确保目录存在
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(QUEUE_DIR, exist_ok=True)

# Bot Token
TOKEN = open(os.path.join(DATA_DIR, "token.txt")).read().strip()

# 支持的语音列表
VOICES = {
    "中文女声": "zh-CN-XiaoxiaoNeural",
    "中文男声": "zh-CN-YunxiNeural",
    "英文女声": "en-US-JennyNeural",
    "英文男声": "en-US-GuyNeural"
}

# 用户语音设置（默认中文女声）
user_voices = {}

async def text_to_speech(text: str, output_file: str, voice: str):
    """使用 edge-tts 转换文字为语音"""
    logger.debug(f"TTS 转换开始: text='{text[:50]}...', voice={voice}, output={output_file}")
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)
    logger.debug(f"TTS 转换完成: {output_file}, 文件大小={os.path.getsize(output_file)} bytes")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    logger.info(f"用户启动 bot: user_id={user_id}, username=@{username}")
    
    user_voices[user_id] = VOICES["中文女声"]  # 设置默认语音
    logger.debug(f"设置默认语音: user_id={user_id}, voice={VOICES['中文女声']}")
    
    await update.message.reply_text(
        "👋 你好！我是 W3C TTS Bot\n\n"
        "📝 发送文字 → 我会转换成语音\n"
        "🎙️ 发送语音 → 我会转换成文字\n\n"
        "🎙️ 命令：\n"
        "/start - 显示帮助\n"
        "/voice - 查看和切换语音\n\n"
        "支持中文和英文，快来试试吧！"
    )

async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /voice 命令"""
    user_id = update.effective_user.id
    logger.debug(f"语音切换命令: user_id={user_id}, args={context.args}")
    
    # 如果有参数，切换语音
    if context.args:
        voice_name = " ".join(context.args)
        if voice_name in VOICES:
            user_voices[user_id] = VOICES[voice_name]
            logger.info(f"用户切换语音: user_id={user_id}, voice={voice_name} ({VOICES[voice_name]})")
            await update.message.reply_text(f"✅ 已切换到：{voice_name}")
        else:
            logger.warning(f"无效语音选择: user_id={user_id}, voice={voice_name}")
            await update.message.reply_text(
                f"❌ 未知语音：{voice_name}\n\n"
                f"可用语音：\n" + "\n".join([f"- {v}" for v in VOICES.keys()])
            )
    else:
        # 显示当前语音和可用选项
        current = [k for k, v in VOICES.items() if v == user_voices.get(user_id, VOICES["中文女声"])][0]
        logger.debug(f"查询当前语音: user_id={user_id}, current={current}")
        await update.message.reply_text(
            f"🎙️ 当前语音：{current}\n\n"
            f"可用语音：\n" + "\n".join([f"- {v}" for v in VOICES.keys()]) +
            f"\n\n使用方法：/voice 中文男声"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理文字消息，转换为语音"""
    text = update.message.text
    user_id = update.effective_user.id
    
    if not text:
        return
    
    logger.info(f"收到文字消息: user_id={user_id}, text_length={len(text)}, text='{text[:100]}...'")
    
    # 获取用户语音设置
    voice = user_voices.get(user_id, VOICES["中文女声"])
    logger.debug(f"使用语音: {voice}")
    
    # 发送处理中提示
    msg = await update.message.reply_text("🎙️ 正在生成语音...")
    
    try:
        # 生成语音文件
        output_file = f"/tmp/tts_{update.message.message_id}.mp3"
        logger.debug(f"生成语音文件: {output_file}")
        await text_to_speech(text, output_file, voice)
        
        # 发送语音
        logger.debug(f"发送语音消息: file_size={os.path.getsize(output_file)} bytes")
        with open(output_file, 'rb') as audio:
            await update.message.reply_voice(audio)
        
        # 删除临时文件
        os.remove(output_file)
        logger.debug(f"临时文件已删除: {output_file}")
        
        # 删除处理中提示
        await msg.delete()
        logger.info(f"TTS 处理成功: user_id={user_id}, message_id={update.message.message_id}")
        
    except Exception as e:
        logger.error(f"TTS 处理失败: user_id={user_id}, error={e}", exc_info=True)
        await msg.edit_text(f"❌ 生成失败: {str(e)}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理语音消息，调用 API 识别后发送到 tmux"""
    user_id = update.effective_user.id
    logger.info(f"收到语音消息: user_id={user_id}, duration={update.message.voice.duration}s")
    
    msg = await update.message.reply_text("🎧 正在识别语音...")
    
    try:
        # 下载语音文件
        voice_file = await update.message.voice.get_file()
        file_path = f"/tmp/voice_{update.message.message_id}.ogg"
        await voice_file.download_to_drive(file_path)
        
        # 调用 API 识别语音
        import aiohttp
        async with aiohttp.ClientSession() as session:
            with open(file_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename='voice.ogg')
                async with session.post('http://localhost:15001/voice_to_text', data=data) as resp:
                    result = await resp.json()
                    text = result['text']
        
        os.remove(file_path)
        logger.info(f"语音识别成功: text='{text}'")
        
        await msg.edit_text(f"📝 识别结果：{text}")
        
        # 发送到 tmux 6:master.0
        subprocess.run(['tmux', 'send-keys', '-t', '6:master.0', text])
        await asyncio.sleep(1)
        subprocess.run(['tmux', 'send-keys', '-t', '6:master.0', 'Enter'])
        logger.info(f"已发送到 tmux 6:master.0: {text}")
        
    except Exception as e:
        logger.error(f"语音处理失败: {e}", exc_info=True)
        await msg.edit_text(f"❌ 处理失败: {str(e)}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理语音消息，调用 API 识别后发送到 tmux"""
    user_id = update.effective_user.id
    logger.info(f"收到语音消息: user_id={user_id}, duration={update.message.voice.duration}s")
    
    msg = await update.message.reply_text("🎧 正在识别语音...")
    
    try:
        # 下载语音文件
        voice_file = await update.message.voice.get_file()
        file_path = f"/tmp/voice_{update.message.message_id}.ogg"
        await voice_file.download_to_drive(file_path)
        
        # 调用 API 识别语音
        async with aiohttp.ClientSession() as session:
            with open(file_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename='voice.ogg')
                async with session.post('http://localhost:15001/voice_to_text', data=data) as resp:
                    result = await resp.json()
                    text = result['text']
        
        os.remove(file_path)
        logger.info(f"语音识别成功: text='{text}'")
        
        await msg.edit_text(f"📝 识别结果：{text}\n\n⏳ 等待回复...")
        
        # 放入队列
        queue_file = os.path.join(QUEUE_DIR, f"msg_{int(time.time())}_{user_id}.json")
        with open(queue_file, 'w') as f:
            json.dump({
                'chat_id': update.message.chat_id,
                'user_id': user_id,
                'text': text,
                'timestamp': time.time()
            }, f)
        
        # 发送到 tmux 6:master.0
        subprocess.run(['tmux', 'send-keys', '-t', '6:master.0', text])
        await asyncio.sleep(1)
        subprocess.run(['tmux', 'send-keys', '-t', '6:master.0', 'Enter'])
        logger.info(f"已发送到 tmux 6:master.0: {text}")
        
    except Exception as e:
        logger.error(f"语音处理失败: {e}", exc_info=True)
        await msg.edit_text(f"❌ 处理失败: {str(e)}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮回调"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('detail_'):
        # 从 API 获取完整文本
        async with aiohttp.ClientSession() as session:
            async with session.get(f'http://localhost:15001/callback/{query.data}') as resp:
                result = await resp.json()
                full_text = result['text']
        
        await query.message.reply_text(full_text)

async def wait_for_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, queue_file: str, msg):
    """等待 kiro-cli 回复"""
    max_wait = 300  # 最多等待 5 分钟
    check_interval = 2  # 每 2 秒检查一次
    waited = 0
    
    while waited < max_wait:
        await asyncio.sleep(check_interval)
        waited += check_interval
        
        # 检查回复文件
        reply_file = queue_file.replace('.json', '_reply.json')
        if os.path.exists(reply_file):
            try:
                with open(reply_file, 'r', encoding='utf-8') as f:
                    reply_data = json.load(f)
                
                reply_text = reply_data.get('reply', '无回复')
                logger.info(f"收到 kiro-cli 回复: {reply_text[:100]}")
                
                # 发送回复
                await update.message.reply_text(reply_text)
                await msg.delete()
                
                # 清理文件
                os.remove(queue_file)
                os.remove(reply_file)
                return
                
            except Exception as e:
                logger.error(f"读取回复失败: {e}", exc_info=True)
                break
    
    # 超时
    await msg.edit_text("⏱️ 等待超时，请稍后再试")
    if os.path.exists(queue_file):
        os.remove(queue_file)

def main():
    """启动 bot"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='W3C TTS Bot - Telegram 文字转语音机器人')
    parser.add_argument('--debug', action='store_true', help='启用调试模式，输出详细日志')
    args = parser.parse_args()
    
    # 配置日志级别
    log_level = logging.DEBUG if args.debug else logging.INFO
    
    # 配置日志格式
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # 创建日志处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format))
    
    # 所有日志文件
    file_handler = logging.FileHandler(os.path.join(LOG_DIR, 'bot.log'), encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(log_format))
    
    # 错误日志文件（只记录 ERROR 和 CRITICAL）
    error_handler = logging.FileHandler(os.path.join(LOG_DIR, 'error.log'), encoding='utf-8')
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(log_format))
    
    # 配置根日志记录器
    logging.basicConfig(
        level=log_level,
        handlers=[console_handler, file_handler, error_handler]
    )
    
    logger.info("=" * 60)
    logger.info("🤖 Starting W3C TTS Bot...")
    logger.info(f"📝 Bot Username: @w3c_tts_bot")
    logger.info(f"🎙️ 支持语音: {', '.join(VOICES.keys())}")
    logger.info(f"🔧 调试模式: {'开启' if args.debug else '关闭'}")
    logger.info(f"📊 日志级别: {logging.getLevelName(log_level)}")
    logger.info(f"📁 数据目录: {DATA_DIR}")
    logger.info(f"📁 日志目录: {LOG_DIR}")
    logger.info(f"📄 日志文件: bot.log (所有), error.log (仅错误)")
    logger.info("=" * 60)
    
    if args.debug:
        logger.debug("调试模式已启用，将输出详细日志")
        logger.debug(f"Token 长度: {len(TOKEN)} 字符")
        logger.debug(f"可用语音列表: {VOICES}")
    
    # 创建应用
    logger.debug("正在创建 Telegram Application...")
    app = Application.builder().token(TOKEN).build()
    
    # 添加处理器
    logger.debug("正在注册命令处理器...")
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("voice", voice_command))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    logger.debug("所有处理器注册完成")
    
    # 启动
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
