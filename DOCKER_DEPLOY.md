# Docker 快速部署

## 一键部署

```bash
# 1. 配置 token
cp .env.example .env
nano .env  # 填入你的 BOT_TOKEN

# 2. 启动
docker-compose up -d

# 3. 查看日志
docker-compose logs -f
```

## 管理命令

```bash
# 查看状态
docker-compose ps

# 停止
docker-compose down

# 重启
docker-compose restart

# 查看日志
docker-compose logs -f tts-bot

# 进入容器
docker-compose exec tts-bot bash
```

## 环境变量

在 `.env` 文件中配置：

```bash
# 必填
BOT_TOKEN=your_telegram_bot_token

# 可选
API_PORT=15001
DATA_DIR=/data
```

## 健康检查

容器会自动检查服务健康状态：
- 检查间隔：30秒
- 超时时间：10秒
- 重试次数：3次

## 数据持久化

数据存储在 `./data` 目录：
- `./data/logs/` - 日志文件
- `./data/queue/` - 任务队列

## 多地部署

**香港服务器**：
```bash
cp .env.example .env.hk
echo "BOT_TOKEN=your_hk_token" > .env.hk
docker-compose -f docker-compose.hk.yml up -d
```

**美国服务器**：
```bash
cp .env.example .env.us
echo "BOT_TOKEN=your_us_token" > .env.us
docker-compose -f docker-compose.yml up -d
```
