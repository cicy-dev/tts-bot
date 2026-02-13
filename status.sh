#!/bin/bash
# TTS Bot 状态检查脚本

echo "📊 TTS Bot 服务状态"
echo ""

# 检查 Bot API
if [ -f /tmp/tts_bot_api.pid ] && ps -p $(cat /tmp/tts_bot_api.pid) > /dev/null 2>&1; then
    echo "✅ Bot API (15001) - 运行中"
    echo "   PID: $(cat /tmp/tts_bot_api.pid)"
else
    echo "❌ Bot API - 未运行"
fi

# 检查 Telegram Bot
if [ -f /tmp/tts_bot.pid ] && ps -p $(cat /tmp/tts_bot.pid) > /dev/null 2>&1; then
    echo "✅ Telegram Bot - 运行中"
    echo "   PID: $(cat /tmp/tts_bot.pid)"
else
    echo "❌ Telegram Bot - 未运行"
fi

# 检查 Handler
if [ -f /tmp/tts_handler.pid ] && ps -p $(cat /tmp/tts_handler.pid) > /dev/null 2>&1; then
    echo "✅ Handler - 运行中"
    echo "   PID: $(cat /tmp/tts_handler.pid)"
else
    echo "❌ Handler - 未运行"
fi

# 检查端口
echo ""
echo "🔌 端口状态："
if netstat -tlnp 2>/dev/null | grep -q ":15001"; then
    echo "✅ 15001 - 监听中"
else
    echo "❌ 15001 - 未监听"
fi

# 显示最近日志
echo ""
echo "📝 最近日志 (最后5行)："
echo ""
echo "--- Bot API ---"
tail -n 5 ~/logs/bot_api.log 2>/dev/null || echo "无日志"
echo ""
echo "--- Telegram Bot ---"
tail -n 5 ~/logs/tts_bot.log 2>/dev/null || echo "无日志"
