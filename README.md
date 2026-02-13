# TTS Bot

Telegram Bot — 接收用户消息（文字/语音），转发给 AI CLI（kiro-cli 等），捕获回复发回 Telegram。

## 架构

```
用户 (Telegram)
    ↓ Bot API polling
bot.py — 收消息，文字直接发 tmux，语音先 STT 再发
    ↓ tmux send-keys
AI CLI (tmux session，如 kiro-cli / claude / gemini)
    ↓
kiro_handler.py — 每 3s capture-pane，检测新回复
    ↓ POST /reply
bot_api.py — 短回复: 语音+caption / 长回复: 纯文字
    ↓ Bot API
用户 (Telegram)
```

## 快速开始

```bash
# 1. 配置
cp .env.example .env
nano .env  # 填入 BOT_TOKEN

# 2. 在 host 上创建 tmux session
tmux new-session -d -s kiro -n master
tmux send-keys -t kiro:master 'kiro-cli' Enter

# 3. 启动
docker-compose up -d

# 4. 查看日志
docker-compose logs -f
```

## 项目结构

```
tts-bot/
├── tts_bot/                  # 核心包
│   ├── bot.py               # Telegram Bot，polling 收消息
│   ├── config.py            # 配置（win_id, 路径等）
│   ├── kiro_tmux_backend.py # tmux 操作（send-keys, capture-pane）
│   ├── redis_queue.py       # Redis 消息队列
│   ├── tmux_backend.py      # tmux 基类
│   ├── stt_backend.py       # STT 基类
│   └── default_stt.py       # 默认 Google STT
├── scripts/
│   ├── bot_api.py           # HTTP API，/reply 发回复到 Telegram
│   └── kiro_handler.py      # 监控 tmux，捕获 AI 回复
├── docker-compose.yml
├── docker-start.sh          # 容器启动脚本（含 auto-reload）
├── Dockerfile
├── requirements.txt
├── .env.example
└── AGENTS.md                # 开发规范
```

## 消息流程

### 文字消息
1. 用户发文字 → bot.py 收到
2. `tmux send-keys` 发到 AI CLI
3. 写 `active_chat_id` 文件
4. 发 "✅ 已发送" 确认（回复到达后自动删除）

### 语音消息
1. 用户发语音 → bot.py 下载 .oga 文件
2. Google STT 识别为文字
3. 显示 "🎤 识别结果"（reply 到用户语音）
4. 识别文字发到 tmux，同文字消息流程

### 回复捕获
1. `kiro_handler.py` 每 3s 执行 `tmux capture-pane`
2. 对比内容 hash 检测变化
3. 提取最后一个 `> ` 前缀的文本块
4. 检测到 `[y/n/t]` 自动发 `t` 授权
5. POST 到 `/reply` API

### 回复发送
- 短回复（≤ `TTS_SHORT_LIMIT` 字）：🔊 语音 + caption
- 长回复：📝 纯文字
- 发送后自动删除 "✅ 已发送" 消息

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BOT_TOKEN` | (必填) | Telegram Bot Token |
| `API_PORT` | `15001` | API 端口 |
| `REDIS_URL` | `redis://redis:6379/0` | Redis 连接 |
| `TMUX_SOCKET` | `/tmp/tmux-1001/default` | tmux socket 路径 |
| `DATA_DIR` | `/data` | 数据目录 |
| `TTS_VOICE` | `zh-CN-YunxiNeural` | edge-tts 语音 |
| `TTS_SHORT_LIMIT` | `200` | 短回复阈值（字数） |

## 开发

### Auto-Reload

`tts_bot/` 和 `scripts/` 目录挂载进容器，修改 `.py` 文件后 3 秒内自动重载。

只有修改 `Dockerfile`、`requirements.txt`、`docker-compose.yml` 才需要重建：

```bash
docker-compose down && docker-compose build --no-cache && docker-compose up -d
```

### 日志

```bash
docker-compose logs -f          # Docker 日志
docker exec tts-bot cat /tmp/bot.log       # Bot
docker exec tts-bot cat /tmp/bot_api.log   # API
docker exec tts-bot cat /tmp/handler.log   # Handler
```

### 查看 tmux 终端

用 ttyd 在浏览器里看 AI CLI 终端：

```bash
ttyd -p 7682 tmux attach-session -t kiro
# 浏览器打开 http://localhost:7682
```

## 管理

```bash
docker-compose ps          # 状态
docker-compose logs -f     # 日志
docker-compose restart     # 重启
docker-compose down        # 停止
```
