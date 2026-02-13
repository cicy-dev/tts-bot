#!/bin/bash
# TTS Bot 一键启动脚本 - 适用于任何 GCP 或机器

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🚀 启动 TTS Bot 服务..."

# 1. 检查并安装依赖
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

# 2. 创建虚拟环境（如果不存在）
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

# 3. 激活虚拟环境并安装依赖
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# 4. 创建必要目录
mkdir -p ~/logs
mkdir -p ~/data/tts-tg-bot/queue
mkdir -p ~/data/tts-tg-bot/audio

# 5. 检查配置文件
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "⚠️  已创建 .env 文件，请配置 TOKEN"
    else
        echo "❌ 缺少 .env 配置文件"
        exit 1
    fi
fi

# 6. 检查 token
if [ ! -f ~/data/tts-tg-bot/token.txt ]; then
    echo "⚠️  请创建 ~/data/tts-tg-bot/token.txt 并填入 Telegram Bot Token"
fi

# 7. 启动 Bot API (15001端口)
echo "🔧 启动 Bot API..."
nohup python3 scripts/bot_api.py > ~/logs/bot_api.log 2>&1 &
echo $! > /tmp/tts_bot_api.pid

# 8. 等待 API 启动
sleep 3

# 9. 启动 Telegram Bot
echo "🤖 启动 Telegram Bot..."
nohup python3 -m tts_bot.bot > ~/logs/tts_bot.log 2>&1 &
echo $! > /tmp/tts_bot.pid

# 10. 启动 Handler
echo "⚙️  启动 Handler..."
nohup python3 -m tts_bot.kiro_handler > ~/logs/kiro_handler.log 2>&1 &
echo $! > /tmp/tts_handler.pid

sleep 2

# 11. 检查服务状态
echo ""
echo "✅ 服务启动完成！"
echo ""
echo "📊 服务状态："

if ps -p $(cat /tmp/tts_bot_api.pid 2>/dev/null) > /dev/null 2>&1; then
    echo "  ✅ Bot API (15001) - 运行中"
else
    echo "  ❌ Bot API - 启动失败"
fi

if ps -p $(cat /tmp/tts_bot.pid 2>/dev/null) > /dev/null 2>&1; then
    echo "  ✅ Telegram Bot - 运行中"
else
    echo "  ❌ Telegram Bot - 启动失败"
fi

if ps -p $(cat /tmp/tts_handler.pid 2>/dev/null) > /dev/null 2>&1; then
    echo "  ✅ Handler - 运行中"
else
    echo "  ❌ Handler - 启动失败"
fi

echo ""
echo "📝 日志位置："
echo "  - Bot API: ~/logs/bot_api.log"
echo "  - Bot: ~/logs/tts_bot.log"
echo "  - Handler: ~/logs/kiro_handler.log"
echo ""
echo "🛑 停止服务: bash stop.sh"
echo "📊 查看状态: bash status.sh"
