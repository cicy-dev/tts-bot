#!/bin/bash
# Docker 容器启动脚本 - 非阻塞模式

set -e

# 启动 Bot API（后台）
python3 scripts/bot_api.py > /tmp/bot_api.log 2>&1 &
API_PID=$!

# 等待 API 启动
sleep 3

# 启动 Bot（后台）
python3 -m tts_bot.bot > /tmp/bot.log 2>&1 &
BOT_PID=$!

# 启动 Handler（后台）
python3 scripts/kiro_handler.py > /tmp/handler.log 2>&1 &
HANDLER_PID=$!

echo "✅ 所有服务已启动"
echo "API PID: $API_PID"
echo "Bot PID: $BOT_PID"
echo "Handler PID: $HANDLER_PID"

# 监控进程，任何一个退出就重启
while true; do
  if ! kill -0 $API_PID 2>/dev/null; then
    echo "⚠️ API 崩溃，重启中..."
    python3 scripts/bot_api.py > /tmp/bot_api.log 2>&1 &
    API_PID=$!
  fi
  
  if ! kill -0 $BOT_PID 2>/dev/null; then
    echo "⚠️ Bot 崩溃，重启中..."
    python3 -m tts_bot.bot > /tmp/bot.log 2>&1 &
    BOT_PID=$!
  fi
  
  if ! kill -0 $HANDLER_PID 2>/dev/null; then
    echo "⚠️ Handler 崩溃，重启中..."
    python3 scripts/kiro_handler.py > /tmp/handler.log 2>&1 &
    HANDLER_PID=$!
  fi
  
  sleep 10
done
