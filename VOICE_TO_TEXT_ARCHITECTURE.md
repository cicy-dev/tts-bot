# TTS Bot 语音转文字架构文档

## 📋 系统概览

```
用户语音消息 (Telegram)
    ↓
┌─────────────────────────────────────────────────────────┐
│  bot.py (主程序)                                         │
│  - 接收Telegram消息                                      │
│  - 下载语音文件到 /tmp/voice_xxx.ogg                     │
│  - 调用 STT Backend                                      │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│  default_stt.py (STT后端)                               │
│  - 封装HTTP请求                                          │
│  - 上传音频到 http://localhost:15001/voice_to_text      │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│  bot_api.py (API服务器 - 端口15001)                     │
│  1. 接收音频文件 (.ogg)                                  │
│  2. 转换为 WAV 格式 (pydub)                              │
│  3. 调用 Google Speech API                               │
│  4. 返回识别文字                                         │
└─────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────┐
│  Google Speech Recognition API                          │
│  - 免费在线服务                                          │
│  - 支持中文 (zh-CN) 和英文 (en-US)                      │
└─────────────────────────────────────────────────────────┘
    ↓
识别结果返回 → 更新队列 → 发送到Telegram
```

## 🔄 详细流程

### 第1步：接收语音消息
**文件**: `tts_bot/bot.py` (第429行)
**函数**: `handle_voice()`

```python
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. 获取消息信息
    user_id = update.effective_user.id
    message_id = update.message.message_id
    
    # 2. 创建队列文件
    queue_file = create_a_queue_file(...)
    
    # 3. 发送ACK消息
    ack_msg = await update.message.reply_text("🎧 识别中...")
    
    # 4. 下载语音文件
    voice_file = await update.message.voice.get_file()
    file_path = f"/tmp/voice_{message_id}.ogg"
    await voice_file.download_to_drive(file_path)
    
    # 5. 调用STT识别
    stt = get_stt_backend()
    text = await stt.recognize(file_path)
```

**输入**: Telegram语音消息 (.oga/.ogg)
**输出**: 下载到 `/tmp/voice_xxx.ogg`

---

### 第2步：STT后端调用
**文件**: `tts_bot/default_stt.py`
**类**: `DefaultSTTBackend`

```python
class DefaultSTTBackend(STTBackend):
    API_URL = "http://localhost:15001/voice_to_text"
    
    async def recognize(self, audio_path: str) -> str:
        # 1. 打开音频文件
        # 2. 构造multipart/form-data请求
        # 3. POST到API服务器
        # 4. 返回识别结果
        
        async with aiohttp.ClientSession() as session:
            with open(audio_path, "rb") as f:
                data = aiohttp.FormData()
                data.add_field("file", f, filename="voice.ogg")
                async with session.post(self.API_URL, data=data) as resp:
                    result = await resp.json()
                    return result.get("text", "")
```

**输入**: `/tmp/voice_xxx.ogg`
**输出**: HTTP POST请求到15001端口

---

### 第3步：API服务器处理
**文件**: `scripts/bot_api.py` (第129行)
**端点**: `POST /voice_to_text`
**端口**: 15001

```python
@app.post('/voice_to_text')
async def voice_to_text(file: UploadFile = File(...)):
    # 1. 保存上传的文件
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, 'wb') as f:
        f.write(await file.read())
    
    # 2. 转换为WAV格式
    audio = AudioSegment.from_file(temp_path)
    wav_path = temp_path.replace('.ogg', '.wav')
    audio.export(wav_path, format='wav')
    
    # 3. 语音识别
    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio_data = recognizer.record(source)
        try:
            # 先尝试中文
            text = recognizer.recognize_google(audio_data, language='zh-CN')
        except:
            # 失败则尝试英文
            text = recognizer.recognize_google(audio_data, language='en-US')
    
    # 4. 清理临时文件
    os.remove(temp_path)
    os.remove(wav_path)
    
    # 5. 返回结果
    return {'text': text}
```

**输入**: .ogg音频文件
**处理**:
1. 保存到 `/tmp/`
2. 转换为 WAV
3. 调用Google API
4. 清理临时文件

**输出**: `{'text': '识别的文字'}`

---

### 第4步：Google语音识别
**库**: `speech_recognition`
**API**: Google Speech Recognition (免费)

```python
recognizer = sr.Recognizer()
recognizer.recognize_google(audio_data, language='zh-CN')
```

**支持语言**:
- `zh-CN` - 中文（简体）
- `en-US` - 英文（美国）

**特点**:
- ✅ 免费使用
- ✅ 无需API密钥
- ✅ 在线识别
- ⚠️ 需要网络连接

---

## 📁 文件结构

```
tts-bot/
├── tts_bot/
│   ├── bot.py                 # 主程序，处理Telegram消息
│   ├── stt_backend.py         # STT抽象接口
│   ├── default_stt.py         # 默认STT实现（调用API）
│   └── config.py              # 配置管理
├── scripts/
│   └── bot_api.py             # API服务器（15001端口）
└── data/
    ├── queue/                 # 消息队列
    └── logs/                  # 日志文件
        ├── bot.log            # Bot主日志
        └── error.log          # 错误日志
```

---

## 🔧 技术栈

| 组件 | 技术 | 用途 |
|------|------|------|
| Bot框架 | python-telegram-bot | 接收Telegram消息 |
| 异步框架 | asyncio | 异步处理 |
| HTTP客户端 | aiohttp | 调用API |
| API服务器 | FastAPI + Uvicorn | 提供HTTP接口 |
| 音频处理 | pydub (AudioSegment) | 格式转换 |
| 语音识别 | speech_recognition | Google API封装 |
| 音频格式 | .ogg → .wav | 兼容性转换 |

---

## 🌐 网络通信

### 内部通信
```
bot.py (客户端)
    ↓ HTTP POST
    ↓ multipart/form-data
    ↓ file: voice.ogg
bot_api.py (服务端)
    ↓ 返回 JSON
    ↓ {'text': '识别结果'}
bot.py (接收)
```

### 外部通信
```
bot_api.py
    ↓ HTTPS
    ↓ 音频数据
Google Speech API
    ↓ 返回文字
bot_api.py
```

---

## 📊 数据流

```
1. Telegram消息对象
   ↓
2. /tmp/voice_123.ogg (下载)
   ↓
3. HTTP POST (上传到15001)
   ↓
4. /tmp/voice_123.ogg (API服务器)
   ↓
5. /tmp/voice_123.wav (转换)
   ↓
6. Google API (识别)
   ↓
7. {'text': '结果'} (JSON)
   ↓
8. 队列文件更新
   ↓
9. Telegram消息回复
```

---

## 🔑 关键配置

### 环境变量
```bash
BOT_TOKEN=xxx                    # Telegram Bot Token
DATA_DIR=~/data/tts-tg-bot       # 数据目录
```

### 端口
- **15001** - bot_api.py (语音识别API)
- **Telegram API** - 外部服务

### 临时文件
- `/tmp/voice_*.ogg` - 下载的语音
- `/tmp/voice_*.wav` - 转换后的音频
- 处理完自动删除

---

## 📝 日志

### Bot主日志
**位置**: `~/data/tts-tg-bot/logs/bot.log`
**内容**:
```
2026-02-13 06:07:44 - 收到语音消息: user_id=xxx, duration=1s
2026-02-13 06:07:45 - 下载语音文件: /tmp/voice_xxx.ogg
2026-02-13 06:07:46 - 语音识别成功: text='测试'
```

### API服务日志
**位置**: `/tmp/bot_api.log`
**内容**:
```
INFO: Uvicorn running on http://0.0.0.0:15001
INFO: Started server process
```

### 实时查看
```bash
# Bot日志
tail -f ~/data/tts-tg-bot/logs/bot.log

# API日志
tail -f /tmp/bot_api.log
```

---

## 🚀 启动流程

### 1. 启动API服务器
```bash
cd /home/w3c_offical/projects/tts-bot
python3 scripts/bot_api.py
```
监听端口: 15001

### 2. 启动Bot
```bash
cd /home/w3c_offical/projects/tts-bot
python3 -m tts_bot.bot
```

### 3. 验证
```bash
# 检查端口
netstat -tlnp | grep 15001

# 检查进程
ps aux | grep bot_api.py
ps aux | grep "tts_bot.bot"
```

---

## ⚠️ 依赖项

### Python包
```txt
python-telegram-bot    # Telegram Bot API
fastapi               # API服务器
uvicorn               # ASGI服务器
aiohttp               # 异步HTTP客户端
pydub                 # 音频处理
SpeechRecognition     # 语音识别
edge-tts              # 文字转语音
```

### 系统依赖
```bash
# 音频处理
apt-get install ffmpeg

# Python环境
python3 >= 3.8
```

---

## 🔍 故障排查

### 问题1: 识别失败
**原因**: 
- 网络问题（无法访问Google API）
- 音频格式不支持
- 音频质量太差

**解决**:
```bash
# 检查网络
curl https://www.google.com

# 查看错误日志
tail -f ~/data/tts-tg-bot/logs/error.log
```

### 问题2: API服务未启动
**检查**:
```bash
netstat -tlnp | grep 15001
```

**启动**:
```bash
cd /home/w3c_offical/projects/tts-bot
python3 scripts/bot_api.py
```

### 问题3: 临时文件堆积
**清理**:
```bash
rm -f /tmp/voice_*.ogg /tmp/voice_*.wav
```

---

## 📈 性能指标

- **识别速度**: 1-3秒（取决于网络）
- **支持时长**: 无限制（Google API限制）
- **并发处理**: 支持（异步）
- **准确率**: 取决于Google API

---

## 🔐 安全考虑

1. **临时文件**: 处理后立即删除
2. **API访问**: 仅本地访问（localhost）
3. **Token保护**: 环境变量或文件存储
4. **日志脱敏**: 不记录敏感信息

---

## 📚 扩展性

### 支持其他STT服务
实现 `STTBackend` 接口:

```python
class CustomSTTBackend(STTBackend):
    async def recognize(self, audio_path: str) -> str:
        # 自定义实现
        pass
```

### 支持其他语言
修改 `bot_api.py`:
```python
text = recognizer.recognize_google(audio_data, language='ja-JP')  # 日语
```

---

**文档版本**: 1.0
**创建时间**: 2026-02-13
**维护者**: Kiro Commander
