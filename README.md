# TTS Bot

Telegram Bot，接收用户消息，转发给 kiro-cli（运行在 tmux 中），捕获回复并发回 Telegram。

## 架构

```
用户 (Telegram)
    ↓ Bot API polling
bot.py — 收消息，tmux send-keys 发给 kiro-cli
    ↓
kiro-cli (tmux session: kiro:master.0)
    ↓
kiro_handler.py — 每 3 秒 capture-pane，检测新回复
    ↓ POST /reply
bot_api.py — Bot API sendMessage 发回 Telegram
    ↓
用户 (Telegram)
```

## 快速部署

```bash
# 1. 配置
cp .env.example .env
nano .env  # 填入 BOT_TOKEN

# 2. 创建 tmux + kiro-cli
tmux new-session -d -s kiro -n master
tmux send-keys -t kiro:master 'kiro-cli' Enter

# 3. 启动
docker-compose up -d

# 4. 查看日志
docker-compose logs -f
```

## 核心组件

| 文件 | 作用 |
|------|------|
| `tts_bot/bot.py` | Telegram Bot，polling 收消息，发到 tmux |
| `scripts/bot_api.py` | HTTP API，`/reply` 端点用 Bot API 发回复 |
| `scripts/kiro_handler.py` | 监控 tmux 输出，捕获 kiro-cli 回复 |
| `tts_bot/kiro_tmux_backend.py` | tmux 操作封装（send-keys, capture-pane） |
| `tts_bot/redis_queue.py` | Redis 消息队列 |
| `tts_bot/config.py` | 配置（win_id, 路径等） |

## 回复捕获机制

`kiro_handler.py` 工作原理：
1. 每 3 秒执行 `tmux capture-pane`
2. 对比内容 hash，检测变化
3. 提取最后一个 `> ` 前缀的文本块（kiro-cli 回复格式）
4. 跳过 `λ >` 提示符和 `▸ Credits:` 行
5. 防重复：如果回复已在上次快照中出现则跳过
6. POST 到 `/reply` API 发回 Telegram

## 开发模式（Auto-Reload）

源码目录已挂载进容器，修改 `tts_bot/` 或 `scripts/` 下的 `.py` 文件后 3 秒内自动重载，无需 `docker-compose build`。

只有修改 `Dockerfile`、`requirements.txt`、`docker-compose.yml` 才需要重建。

## 环境变量

| 变量 | 说明 |
|------|------|
| `BOT_TOKEN` | Telegram Bot Token |
| `API_PORT` | API 端口（默认 15001） |
| `REDIS_URL` | Redis 连接（默认 redis://redis:6379/0） |
| `TMUX_SOCKET` | tmux socket 路径 |
| `DATA_DIR` | 数据目录（默认 /data） |

## 管理命令

```bash
docker-compose ps        # 状态
docker-compose logs -f   # 日志
docker-compose restart   # 重启
docker-compose down      # 停止
```

### 容器内日志

```bash
docker exec tts-bot cat /tmp/bot.log       # Bot 日志
docker exec tts-bot cat /tmp/bot_api.log   # API 日志
docker exec tts-bot cat /tmp/handler.log   # Handler 日志
```
