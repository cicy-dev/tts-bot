# 部署指南

## 前置条件

- Docker + Docker Compose
- tmux
- ttyd（可选，浏览器看终端）

## 部署步骤

### 1. 克隆项目

```bash
git clone git@github.com:cicy-dev/tts-bot.git
cd tts-bot
```

### 2. 配置环境变量

```bash
cp .env.example .env
nano .env
```

必填：
```
BOT_TOKEN=你的Telegram Bot Token
```

可选：
```
API_PORT=15001
TTS_VOICE=zh-CN-YunxiNeural
TTS_SHORT_LIMIT=200
```

### 3. 创建 tmux session

```bash
# 创建 session，启动 AI CLI
tmux new-session -d -s kiro -n master
tmux send-keys -t kiro:master 'kiro-cli' Enter

# 验证
tmux capture-pane -t kiro:master -p | tail -3
```

支持任何 AI CLI：kiro-cli、claude、gemini、opencode 等。

### 4. 启动服务

```bash
docker-compose up -d
```

### 5. 验证

```bash
# 健康检查
curl http://localhost:15001/health

# 查看日志
docker-compose logs -f
```

### 6. 可选：ttyd 终端查看

```bash
# 安装
sudo apt install ttyd

# 启动（只读模式）
ttyd -p 7682 tmux attach-session -t kiro

# 浏览器打开 http://localhost:7682
```

## 服务架构

```
docker-compose up -d
├── tts-redis    Redis 队列
└── tts-bot      Bot 容器
    ├── bot_api.py        HTTP API (:15001)
    ├── bot.py            Telegram polling
    └── kiro_handler.py   tmux 回复捕获
```

## 端口

| 端口 | 服务 | 说明 |
|------|------|------|
| 15001 | bot_api | HTTP API（/health, /reply） |
| 6379 | redis | 消息队列（容器内部） |
| 7682 | ttyd | 终端查看（可选） |

## 更新

代码修改自动重载（`tts_bot/`、`scripts/` 下的 `.py` 文件）。

需要重建的情况：
```bash
# 修改了 Dockerfile / requirements.txt / docker-compose.yml
docker-compose down && docker-compose build --no-cache && docker-compose up -d
```

## 故障排查

```bash
# 检查服务状态
docker-compose ps
curl http://localhost:15001/health

# 检查日志
docker exec tts-bot cat /tmp/bot.log | tail -20
docker exec tts-bot cat /tmp/bot_api.log | tail -20
docker exec tts-bot cat /tmp/handler.log | tail -20

# 检查 tmux 连接
docker exec tts-bot python3 -c "
from tts_bot.kiro_tmux_backend import KiroTmuxBackend
from tts_bot.config import config
t = KiroTmuxBackend()
print(t.capture_pane(config.win_id, max_rows=3))
"

# 检查 handler 进程
docker exec tts-bot ps aux | grep handler
```
