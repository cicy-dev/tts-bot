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

app = FastAPI()

# 加载 tts_bot 包
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

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
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

# Bot 实例缓存 {bot_name: Bot}
_bot_cache: dict[str, Bot] = {}


def get_bot_by_name(bot_name: str) -> Bot:
    """根据 bot_name 获取对应 bot（MySQL bot_config → 默认）"""
    if not bot_name:
        return bot
    if bot_name in _bot_cache:
        return _bot_cache[bot_name]
    # 从 MySQL bot_config 获取 bot token
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from tts_bot.session_map import session_map
        mapping = session_map.get_all()
        for win_id, info in mapping.items():
            if info.get("bot_name") == bot_name:
                token = info.get("bot_token")
                if token:
                    _bot_cache[bot_name] = Bot(token=token)
                    return _bot_cache[bot_name]
    except Exception:
        pass
    return bot

# 存储完整消息
full_messages = {}

class Reply(BaseModel):
    message_id: str
    reply: str
    chat_id: int
    full_text: str = None
    bot_name: str = ""

@app.get('/health')
def health():
    """健康检查"""
    import pymysql
    try:
        mysql_pass = os.getenv("MYSQL_PASSWORD", "")
        conn = pymysql.connect(host='localhost', user='root', password=mysql_pass, database='tts_bot')
        conn.close()
        return {'status': 'ok', 'mysql': True}
    except:
        return {'status': 'ok', 'mysql': False}

@app.get('/messages')
def get_messages():
    """获取待处理的消息（从 MySQL qa_pair）"""
    try:
        import pymysql
        mysql_pass = os.getenv("MYSQL_PASSWORD", "")
        conn = pymysql.connect(host='localhost', user='root', password=mysql_pass, database='tts_bot', charset='utf8mb4')
        c = conn.cursor()
        c.execute("SELECT id, question, status, created_at FROM qa_pair WHERE status='pending' ORDER BY created_at ASC LIMIT 20")
        messages = [{'id': r[0], 'text': r[1], 'status': r[2], 'timestamp': str(r[3])} for r in c.fetchall()]
        c.close()
        conn.close()
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
    """语音转文字 - 调用 STT API(:15003)"""
    try:
        import aiohttp
        file_bytes = await file.read()
        data = aiohttp.FormData()
        data.add_field('file', file_bytes, filename=file.filename, content_type='audio/ogg')
        async with aiohttp.ClientSession() as session:
            async with session.post('http://localhost:15003/stt', data=data) as resp:
                result = await resp.json()
        if result.get('error'):
            return {'error': result['error']}
        return {'text': result.get('text', '')}
    except Exception as e:
        return {'error': str(e)}

import re
import tempfile


def md_to_tg_html(text: str) -> str:
    """Markdown → Telegram HTML 转换"""
    # 保护代码块
    code_blocks = []
    def save_code(m):
        code_blocks.append(m.group(1))
        return f"__CODE_BLOCK_{len(code_blocks)-1}__"
    text = re.sub(r'```(?:\w*)\n?(.*?)```', save_code, text, flags=re.DOTALL)

    inline_codes = []
    def save_inline(m):
        inline_codes.append(m.group(1))
        return f"__INLINE_CODE_{len(inline_codes)-1}__"
    text = re.sub(r'`([^`]+)`', save_inline, text)

    # Markdown 表格 → 可读文本
    def convert_table(m):
        lines = m.group(0).strip().split('\n')
        rows = []
        for line in lines:
            cells = [c.strip() for c in line.strip('|').split('|')]
            if all(re.match(r'^[-:]+$', c) for c in cells):
                continue  # 跳过分隔行
            rows.append(cells)
        if not rows:
            return m.group(0)
        # 用 header: value 格式
        if len(rows) > 1:
            headers = rows[0]
            result = []
            for row in rows[1:]:
                parts = [f"{headers[i]}: {row[i]}" for i in range(min(len(headers), len(row))) if row[i]]
                result.append(' | '.join(parts))
            return '\n'.join(result)
        return ' | '.join(rows[0])
    text = re.sub(r'(?:^\|.+\|$\n?)+', convert_table, text, flags=re.MULTILINE)

    # 转义 HTML
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Markdown → HTML
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__(?!CODE|INLINE)', r'<i>\1</i>', text)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)

    # 恢复代码块
    for i, code in enumerate(code_blocks):
        code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        text = text.replace(f"__CODE_BLOCK_{i}__", f"<pre>{code}</pre>")
    for i, code in enumerate(inline_codes):
        code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        text = text.replace(f"__INLINE_CODE_{i}__", f"<code>{code}</code>")

    return text

TTS_VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
SHORT_LIMIT = int(os.environ.get("TTS_SHORT_LIMIT", "200"))

# 动态语音配置文件
VOICE_CONFIG_FILE = os.path.join(DATA_DIR, "tts_voice.txt")


def get_tts_voice() -> str:
    """获取当前 TTS 语音（优先读配置文件）"""
    try:
        if os.path.exists(VOICE_CONFIG_FILE):
            with open(VOICE_CONFIG_FILE) as f:
                return f.read().strip()
    except Exception:
        pass
    return TTS_VOICE


def set_tts_voice(voice: str):
    """设置 TTS 语音"""
    with open(VOICE_CONFIG_FILE, "w") as f:
        f.write(voice)


def strip_emoji(text: str) -> str:
    """去掉 emoji 和特殊符号"""
    return re.sub(
        r'[\U0001F000-\U0001FFFF\U00002702-\U000027B0\U0000FE00-\U0000FE0F\U0000200D\U00002600-\U000026FF\U00002B50-\U00002B55]+',
        '', text
    ).strip()

def split_reply(text: str):
    """拆分回复：短摘要(TTS用) + 详细内容"""
    if len(text) <= SHORT_LIMIT:
        return text, None

    # 提取第一句话作为摘要
    import re
    # 按中英文句号、感叹号、问号分割
    match = re.search(r'[。！？.!?]', text)
    if match and match.end() <= SHORT_LIMIT * 2:
        summary = text[:match.end()]
    else:
        # 没找到句号就取前 SHORT_LIMIT 字 + "..."
        summary = text[:SHORT_LIMIT] + "..."

    return summary, text

@app.post('/set_voice')
async def api_set_voice(data: dict):
    """设置 TTS 语音"""
    voice = data.get('voice', '')
    if voice:
        set_tts_voice(voice)
        return {'success': True, 'voice': voice}
    return {'success': False, 'current': get_tts_voice()}


@app.get('/get_voice')
async def api_get_voice():
    """获取当前 TTS 语音"""
    return {'voice': get_tts_voice()}


@app.post('/typing')
async def post_typing(data: dict):
    """发送 typing 状态"""
    bot_name = data.get("bot_name", "")
    chat_id = data.get("chat_id", 0)
    if not chat_id:
        return {"success": False, "message": "no chat_id"}
    send_bot = get_bot_by_name(bot_name)
    try:
        await send_bot.send_chat_action(chat_id=chat_id, action="typing")
        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post('/reply')
async def post_reply(reply: Reply):
    """提交回复：根据 bot_name 找到对应 bot 发送"""
    print(f"收到回复: bot={reply.bot_name}, chat={reply.chat_id}, len={len(reply.reply)}", flush=True)

    # 根据 bot_name 获取对应的 bot 实例
    send_bot = get_bot_by_name(reply.bot_name)

    import sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from tts_bot.session_map import session_map
    TTS_ENABLED = session_map.get_var("tts_enabled", "0") == "1"

    try:
        summary, detail = split_reply(reply.reply)

        if detail or not TTS_ENABLED:
            await send_bot.send_message(chat_id=reply.chat_id, text=md_to_tg_html(reply.reply if detail else summary), parse_mode='HTML')
        else:
            # 短回复：语音 + caption
            try:
                html_summary = md_to_tg_html(summary)
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post('http://localhost:15002/tts',
                        json={"text": strip_emoji(summary)}) as resp:
                        tts_data = await resp.read()
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    f.write(tts_data)
                    tts_path = f.name
                with open(tts_path, "rb") as audio:
                    await send_bot.send_voice(chat_id=reply.chat_id, voice=audio, caption=html_summary, parse_mode='HTML')
                os.remove(tts_path)
            except Exception as e:
                print(f"TTS 失败: {e}", flush=True)
                await send_bot.send_message(chat_id=reply.chat_id, text=html_summary, parse_mode='HTML')

        # 删除 "已发送" ack 消息
        ack_file = os.path.join(os.environ.get("DATA_DIR", "/data"), "ack_message_id")
        try:
            if os.path.exists(ack_file):
                with open(ack_file) as f:
                    ack_id = int(f.read().strip())
                await send_bot.delete_message(chat_id=reply.chat_id, message_id=ack_id)
                os.remove(ack_file)
        except Exception:
            pass

        return {'success': True, 'message': 'Message sent'}
    except Exception as e:
        print(f"发送失败: {e}", flush=True)
        return {'success': False, 'error': str(e)}

class AuthRequest(BaseModel):
    chat_id: int = 0
    bot_name: str = ""
    win_id: str = ""
    context: str = ""
    auth_bot: str = ""


@app.post('/auth_request')
async def post_auth_request(req: AuthRequest):
    """handler 上报 [y/n/t]，发送 inline keyboard 给用户决策"""
    send_bot = get_bot_by_name(req.bot_name)
    try:
        ctx_lines = req.context.strip().split("\n")[-5:]
        ctx_short = "\n".join(ctx_lines)

        text = f"🔐 <b>{req.bot_name}</b> 请求授权\n<pre>{ctx_short}</pre>"
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Trust", callback_data=f"auth_t_{req.win_id}"),
                InlineKeyboardButton("👍 Yes", callback_data=f"auth_y_{req.win_id}"),
                InlineKeyboardButton("❌ No", callback_data=f"auth_n_{req.win_id}"),
            ]
        ])
        await send_bot.send_message(
            chat_id=req.chat_id, text=text,
            reply_markup=buttons, parse_mode='HTML'
        )
        return {'success': True}
    except Exception as e:
        print(f"授权请求发送失败: {e}", flush=True)
        return {'success': False, 'error': str(e)}


@app.post('/auth_log')
async def post_auth_log(req: AuthRequest):
    """auth bot 记录授权事件（handler 已自动发 t）"""
    try:
        auth_bot_obj = get_bot_by_name(req.auth_bot)
        chat_id = req.chat_id or int(os.getenv("CHAT_ID", "0"))
        if not chat_id:
            return {'success': False, 'error': 'no chat_id for auth bot'}

        ctx_lines = req.context.strip().split("\n")[-3:]
        ctx_short = "\n".join(ctx_lines)
        text = f"🔓 自动授权 <b>t</b>\n📍 {req.bot_name} → {req.win_id}\n<pre>{ctx_short}</pre>"
        await auth_bot_obj.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
        return {'success': True}
    except Exception as e:
        print(f"auth_log 发送失败: {e}", flush=True)
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
