#!/usr/bin/env python3
"""接收 Telegram 语音消息并转文字"""
import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import speech_recognition as sr
from pydub import AudioSegment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8170423748:AAGg93MOqQJDaf9wAsR9dIHQwS3uxRGDjt0"

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理语音消息"""
    try:
        # 下载语音
        voice = await update.message.voice.get_file()
        voice_path = f"/tmp/voice_{update.message.message_id}.ogg"
        await voice.download_to_drive(voice_path)
        
        # 转换为 WAV
        wav_path = voice_path.replace('.ogg', '.wav')
        audio = AudioSegment.from_ogg(voice_path)
        audio.export(wav_path, format='wav')
        
        # 识别
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language='zh-CN')
        
        # 回复
        await update.message.reply_text(f"✅ 收到：{text}")
        logger.info(f"Voice recognized: {text}")
        
        # 清理
        os.remove(voice_path)
        os.remove(wav_path)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ 识别失败：{str(e)}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    
    logger.info("🎤 Voice receiver bot started")
    app.run_polling()

if __name__ == '__main__':
    main()
