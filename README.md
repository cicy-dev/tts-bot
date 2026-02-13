# TTS Bot

一个可以部署到任何地方的 Telegram TTS Bot。

## 快速部署

### 1. 配置 Token
```bash
# 复制模板
cp .env.example .env

# 编辑并填入你的 token
nano .env
```

### 2. 启动
```bash
./bot start
```

就这么简单！

## 管理命令

```bash
./bot start    # 启动
./bot stop     # 停止
./bot restart  # 重启
./bot logs     # 查看日志
./bot          # 查看状态
```

## 多地部署示例

**香港服务器**：
```bash
# 1. 克隆项目
git clone <repo>
cd tts-bot

# 2. 配置 token
echo "BOT_TOKEN=你的香港token" > .env

# 3. 启动
./bot start
```

**美国服务器**：
```bash
# 同样的步骤，只是 token 不同
echo "BOT_TOKEN=你的美国token" > .env
./bot start
```

## 功能

- 文字 → 语音
- 语音 → 文字
- 自动重启
- 日志管理

## 要求

- Docker
- Docker Compose

仅此而已！
