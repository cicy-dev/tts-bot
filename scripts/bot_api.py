#!/usr/bin/env python3
"""
Bot HTTP API Server
提供消息队列的 HTTP 接口
"""

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
import sys
import uvicorn
import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler
import speech_recognition as sr
from pydub import AudioSegment

app = FastAPI()

# 加载 tts_bot 包
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tts_bot.redis_queue import rq

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

QUEUE_DIR = os.path.expanduser("~/data/tts-tg-bot/queue")
os.makedirs(QUEUE_DIR, exist_ok=True)

DATA_DIR = os.path.expanduser("~/data/tts-tg-bot")
TOKEN_FILE = os.path.join(DATA_DIR, 'token.txt')

# 读取 bot token（优先环境变量）
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN and os.path.exists(TOKEN_FILE):
    with open(TOKEN_FILE, 'r') as f:
        BOT_TOKEN = f.read().strip()
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found! Set BOT_TOKEN env or create token.txt")

bot = Bot(token=BOT_TOKEN)

# 存储完整消息
full_messages = {}

class Reply(BaseModel):
    message_id: str
    reply: str
    chat_id: int
    full_text: str = None

@app.get('/health')
def health():
    """健康检查"""
    return {'status': 'ok', 'redis': rq.ping()}

@app.get('/messages')
def get_messages():
    """获取待处理的消息（从 Redis）"""
    try:
        pending = rq.client.lrange("tts:queue:pending", 0, -1)
        messages = []
        for msg_id in pending:
            data = rq.get(msg_id)
            if data and data.get('status') == 'pending':
                messages.append({
                    'id': msg_id,
                    'text': data.get('text', ''),
                    'timestamp': data.get('created_at', ''),
                })
        return {'messages': messages}
    except Exception as e:
        return {'messages': [], 'error': str(e)}

@app.post('/open_window')
async def open_window(data: dict):
    """打开浏览器窗口"""
    url = data.get('url', '')
    try:
        import subprocess
        subprocess.run(['open', url], check=True)
        return {'success': True, 'url': url}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.post('/process')
async def process_text(data: dict):
    """处理文字并发送到 AI Studio"""
    text = data.get('text', '')
    
    try:
        import subprocess
        import json
        
        # 输入文字到 AI Studio
        selector = 'body > app-root > ms-app > div > div > div > div > span > ms-console-component > ms-console-embed > div.root > div > div.console-left-panel.visible > ms-code-assistant-chat > div > div.bottom-container > div.input-container > textarea'
        
        # 设置文本
        result = subprocess.run([
            'curl-rpc', 'exec_js',
            'win_id=1',
            f'code=document.querySelector("{selector}").value = "{text}"'
        ], capture_output=True, text=True)
        
        # 触发输入事件
        subprocess.run([
            'curl-rpc', 'exec_js',
            'win_id=1',
            f'code=document.querySelector("{selector}").dispatchEvent(new Event("input", {{bubbles: true}}))'
        ], capture_output=True, text=True)
        
        # 点击发送按钮
        btn_selector = 'body > app-root > ms-app > div > div > div > div > span > ms-console-component > ms-console-embed > div.root > div > div.console-left-panel.visible > ms-code-assistant-chat > div > div.bottom-container > div.input-container > div > div > button.mat-mdc-tooltip-trigger.send-button.ms-button-icon.ms-button-primary.ng-star-inserted'
        
        subprocess.run([
            'curl-rpc', 'exec_js',
            'win_id=1',
            f'code=document.querySelector("{btn_selector}").click()'
        ], capture_output=True, text=True)
        
        return {'text': text, 'reply': f'已发送到 AI Studio: {text}', 'success': True}
    except Exception as e:
        return {'text': text, 'reply': f'错误: {str(e)}', 'success': False}

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
