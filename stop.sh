#!/bin/bash
# TTS Bot 停止脚本

echo "🛑 停止 TTS Bot 服务..."

# 停止所有服务
for pid_file in /tmp/tts_bot_api.pid /tmp/tts_bot.pid /tmp/tts_handler.pid; do
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            kill $pid
            echo "✅ 已停止 PID: $pid"
        fi
        rm "$pid_file"
    fi
done

echo "✅ 所有服务已停止"
