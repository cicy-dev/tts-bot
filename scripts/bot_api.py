#!/usr/bin/env python3
"""
Bot HTTP API Server
提供消息队列的 HTTP 接口
"""

from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
import json
import os
import uvicorn
import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler
import speech_recognition as sr
from pydub import AudioSegment

app = FastAPI()

QUEUE_DIR = os.path.expanduser("~/data/tts-tg-bot/queue")
os.makedirs(QUEUE_DIR, exist_ok=True)

DATA_DIR = os.path.expanduser("~/data/tts-tg-bot")
TOKEN_FILE = os.path.join(DATA_DIR, 'token.txt')

# 读取 bot token
with open(TOKEN_FILE, 'r') as f:
    BOT_TOKEN = f.read().strip()

bot = Bot(token=BOT_TOKEN)

# 存储完整消息
full_messages = {}

class Reply(BaseModel):
    message_id: str
    reply: str
    chat_id: int
    full_text: str = None

@app.get('/messages')
def get_messages():
    """获取待处理的消息"""
    messages = []
    if os.path.exists(QUEUE_DIR):
        files = sorted([f for f in os.listdir(QUEUE_DIR) 
                       if f.endswith('.json') and not f.endswith('_reply.json')])
        
        for filename in files:
            filepath = os.path.join(QUEUE_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('status') == 'pending':
                        messages.append({
                            'id': filename.replace('.json', ''),
                            'text': data['text'],
                            'username': data.get('username', 'Unknown'),
                            'timestamp': data['timestamp']
                        })
            except:
                pass
    
    return {'messages': messages}

@app.post('/voice_to_text')
async def voice_to_text(file: UploadFile = File(...)):
    """语音转文字"""
    try:
        # 保存上传的文件
        temp_path = f"/tmp/{file.filename}"
        with open(temp_path, 'wb') as f:
            f.write(await file.read())
        
        # 转换为 WAV
        audio = AudioSegment.from_file(temp_path)
        wav_path = temp_path.replace('.ogg', '.wav')
        audio.export(wav_path, format='wav')
        
        # 识别
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            try:
                text = recognizer.recognize_google(audio_data, language='zh-CN')
            except:
                text = recognizer.recognize_google(audio_data, language='en-US')
        
        # 清理
        os.remove(temp_path)
        os.remove(wav_path)
        
        return {'text': text}
    except Exception as e:
        return {'error': str(e)}

@app.post('/reply')
async def post_reply(reply: Reply):
    """提交回复并发送到 Telegram"""
    print(f"收到回复: {reply.dict()}", flush=True)
    
    try:
        # 如果有完整文本，添加"查看详情"按钮
        if reply.full_text:
            msg_id = f"{reply.chat_id}_{int(asyncio.get_event_loop().time())}"
            full_messages[msg_id] = reply.full_text
            
            keyboard = [[InlineKeyboardButton("查看详情", callback_data=f"detail_{msg_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await bot.send_message(
                chat_id=reply.chat_id,
                text=reply.reply,
                reply_markup=reply_markup
            )
        else:
            await bot.send_message(
                chat_id=reply.chat_id,
                text=reply.reply
            )
        return {'success': True, 'message': 'Message sent'}
    except Exception as e:
        print(f"发送失败: {e}", flush=True)
        return {'success': False, 'error': str(e)}

@app.get('/callback/{callback_data}')
async def handle_callback(callback_data: str):
    """处理回调查询"""
    if callback_data.startswith('detail_'):
        msg_id = callback_data.replace('detail_', '')
        full_text = full_messages.get(msg_id, '详情已过期')
        return {'text': full_text}
    return {'text': '未知操作'}

if __name__ == '__main__':
    print("🚀 Bot API Server starting on http://localhost:15001")
    uvicorn.run("bot_api:app", host='0.0.0.0', port=15001, reload=True)
