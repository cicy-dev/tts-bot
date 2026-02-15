#!/bin/bash
# Bot Router 服务管理
DIR="/home/w3c_offical/projects/tts-bot/bot-router"
LOG="/tmp/bot_router_node.log"
PID_FILE="/tmp/bot_router_node.pid"

start() {
    echo "❌ Bot Router 已禁用（使用独立 ttyd）"
    return 1
}

stop() {
    pkill -f "node.*index.js" 2>/dev/null
    pkill -f "ttyd -p 130" 2>/dev/null
    echo "stopped"
}

case "${1:-start}" in
    start) start ;;
    stop) stop ;;
    restart) stop; sleep 1; start ;;
    status) ss -tlnp 2>/dev/null | grep ":12345" || echo "not running" ;;
    *) echo "Usage: $0 {start|stop|restart|status}" ;;
esac
