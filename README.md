# TTS Bot

Telegram Bot — 接收用户消息（文字/语音/图片），转发给 AI CLI（kiro-cli / kimi 等），捕获回复发回 Telegram。

## 架构

```
📱 用户 (Telegram)
│
├─ 文字 ──→ bot.py → tmux send-keys → AI CLI
├─ 语音 ──→ bot.py → STT API(:15003) → 文字 → tmux
├─ 图片 ──→ bot.py → OCR(Gemini/OCR.space/EasyOCR) → 文字 → tmux
│
│   ↓ AI 回复
│
├─ kiro_handler.py (每3s轮询 tmux capture-pane)
│   ├─ 对比 hash 检测变化
│   ├─ 检测 [y/n/t] 自动发 t
│   └─ POST /reply
│
└─ bot_api.py
    ├─ md_to_tg_html() 转换格式
    ├─ 短回复: TTS API(:15002) → 语音 + caption
    └─ 长回复: 纯文字
```

## 基础设施

```
~/tools/docker-prod/          ← 生产稳定服务（restart: always）
  ├── prod-redis    :6379     ← Redis 消息队列
  ├── prod-tts      :15002    ← Edge-TTS 文字转语音 API
  └── prod-stt      :15003    ← Google STT 语音转文字 API

~/tools/docker-dev/           ← 开发测试服务
  └── api-easyocr   :15010    ← EasyOCR 图片识别 API

/projects/tts-bot/            ← Bot 本体（轻量化）
  └── tts-bot       :15001    ← Bot + API + Handler
```

## 快速开始

```bash
# 1. 启动基础设施
cd ~/tools/docker-prod && docker-compose up -d

# 2. 配置 Bot
cd /projects/tts-bot
cp .env.example .env
nano .env  # 填入 BOT_TOKEN

# 3. 在 host 上创建 tmux session
tmux new-session -d -s kiro -n master
tmux send-keys -t kiro:master 'kiro-cli' Enter

# 4. 启动 Bot
docker-compose up -d
```

## 项目结构

```
tts-bot/
├── tts_bot/                  # 核心包
│   ├── bot.py               # Telegram Bot (polling, 消息处理, OCR)
│   ├── config.py            # 配置
│   ├── kiro_tmux_backend.py # tmux 操作
│   ├── redis_queue.py       # Redis 队列
│   ├── tmux_backend.py      # tmux 基类
│   ├── stt_backend.py       # STT 基类
│   └── default_stt.py       # Google STT
├── scripts/
│   ├── bot_api.py           # HTTP API (/reply, TTS, md→HTML)
│   └── kiro_handler.py      # tmux 回复捕获
├── bot-router/
│   └── conf/nginx.conf      # Nginx 反代 (端口 12345, ttyd)
├── docker-compose.yml
├── docker-start.sh          # 容器入口 (auto-reload)
├── Dockerfile
├── requirements.txt
├── .env.example
├── AGENTS.md                # 开发规范
└── DEPLOY.md                # 部署指南
```

## 消息流程

### 文字消息
1. 用户发文字 → `bot.py` 收到
2. `tmux send-keys` 发到 kiro:master + kimi:master
3. 发 "💭 Thinking..." ACK（回复到达后自动删除）

### 语音消息
1. 用户发语音 → `bot.py` 下载 .oga
2. STT API(:15003) 识别为文字
3. 显示 "🎤 识别结果"
4. 识别文字发到 tmux

### 图片消息
1. 用户发图片 → `bot.py` 下载
2. OCR 3层 fallback: Gemini API → OCR.space → EasyOCR(:15010)
3. 识别文字发到 tmux
4. 发 "🔍 识别中..." ACK

### 回复捕获 & 发送
1. `kiro_handler.py` 每 3s `capture-pane`
2. 检测变化 → POST `/reply`
3. `bot_api.py` 处理:
   - `md_to_tg_html()` Markdown → Telegram HTML
   - 短回复(≤200字): TTS API(:15002) 生成语音 + caption
   - 长回复: 纯文字

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BOT_TOKEN` | (必填) | Telegram Bot Token |
| `API_PORT` | `15001` | Bot API 端口 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接 |
| `TMUX_SOCKET` | `/tmp/tmux-1001/default` | tmux socket |
| `DATA_DIR` | `/data` | 数据目录 |
| `TTS_VOICE` | `zh-CN-XiaoxiaoNeural` | edge-tts 语音 |
| `TTS_SHORT_LIMIT` | `200` | 短回复阈值 |
| `OWNER_ID` | - | 管理员 Telegram ID |
| `GEMINI_API_KEY` | - | Gemini OCR API Key |
| `OCR_API_KEY` | - | OCR.space API Key |

## 特殊功能

### OWNER_ID 权限控制
- `/start` 显示终端 + VNC 按钮（仅 OWNER）
- `/checklist` 查看工作清单（仅 OWNER）

### HTML 格式化
- 所有消息使用 `parse_mode='HTML'`
- AI 回复自动 Markdown → HTML 转换

### ACK 消息
- 文字: "💭 Thinking..." → 回复到达后删除
- 语音: "🎧 识别中..."
- 图片: "🔍 识别中..."

## 开发

### Auto-Reload
修改 `.py` 文件 → 3 秒内自动重载，无需重启。

仅修改 `Dockerfile`/`requirements.txt`/`docker-compose.yml` 需要重建。

### 日志
```bash
docker exec tts-bot cat /tmp/bot.log       # Bot
docker exec tts-bot cat /tmp/bot_api.log   # API
docker exec tts-bot cat /tmp/handler.log   # Handler
```

### 管理
```bash
docker-compose ps          # 状态
docker-compose logs -f     # 日志
docker-compose restart     # 重启
```
