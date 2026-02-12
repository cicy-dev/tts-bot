#!/usr/bin/env python3
"""
AI Code Generation Service - 赚钱版
接收需求 → Gemini 生成代码 → 交付
支持语音输入 → STT → 发送到 Kiro tmux
支持 TTS 回复
"""
import os
import requests
import subprocess
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import speech_recognition as sr
from pydub import AudioSegment
import edge_tts

TOKEN = "8170423748:AAGg93MOqQJDaf9wAsR9dIHQwS3uxRGDjt0"
GEMINI_API = "http://localhost:8088/generate"
TMUX_WIN_ID = "master:0.0"

def send_to_kiro(text: str):
    """发送消息到 Kiro tmux 窗口"""
    try:
        subprocess.run(
            ["tmux", "send-keys", "-t", TMUX_WIN_ID, text, "Enter"],
            check=True
        )
        print(f"📤 Sent to Kiro: {text[:50]}", flush=True)
    except Exception as e:
        print(f"❌ Failed to send to tmux: {e}", flush=True)

async def text_to_speech(text: str, output_file: str):
    """文字转语音"""
    communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
    await communicate.save(output_file)

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
        
        # 发送到 Kiro
        send_to_kiro(text)
        
        # 回复用户
        voice_file = f"/tmp/reply_{update.message.message_id}.mp3"
        await text_to_speech(text, voice_file)
        with open(voice_file, 'rb') as f:
            await update.message.reply_voice(voice=f)
        os.remove(voice_file)
        
        # 清理
        os.remove(voice_path)
        os.remove(wav_path)
        
    except Exception as e:
        await update.message.reply_text(f"❌ 识别失败：{str(e)}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理文本消息 - 只发送到 Kiro，不回复"""
    user_request = update.message.text
    user_id = update.effective_user.id
    print(f"📩 Text: {user_request[:50]} from {user_id}", flush=True)
    
    # 处理命令
    if user_request == '/web':
        await update.message.reply_text(
            "🎤 语音聊天网页：\nhttps://kyle-column-dependence-ppc.trycloudflare.com\n\n"
            "按住按钮说话，松开发送！"
        )
        return
    
    if user_request == '/vnc':
        await update.message.reply_text(
            "🖥️ VNC 访问地址：\n\n"
            "noVNC Web: https://gcp-6081.cicy.de5.net\n\n"
            "Gotty 终端:\nhttps://quit-proceedings-sys-identifier.trycloudflare.com\n"
            "用户名: w3c\n密码: kiro2026"
        )
        return
    
    # 处理/催命令 - 显示tmux会话列表
    if user_request in ['/催', '催', '显示']:
        try:
            result = subprocess.run(
                ['tmux', 'list-sessions'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                sessions = result.stdout.strip()
                if sessions:
                    response = f"📋 Tmux会话列表：\n\n{sessions}"
                else:
                    response = "⚠️ 当前没有运行的tmux会话"
            else:
                response = f"❌ 获取会话失败：{result.stderr}"
        except subprocess.TimeoutExpired:
            response = "⏱️ 命令超时"
        except Exception as e:
            response = f"❌ 执行失败：{str(e)}"
        
        await update.message.reply_text(response)
        return
    
    # 发送到 Kiro
    send_to_kiro(user_request)
    
    # 不回复任何消息

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("💰 AI Service started!")
    print(f"📍 Sending to tmux: {TMUX_WIN_ID}")
    app.run_polling()

if __name__ == '__main__':
    main()
