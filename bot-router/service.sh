#!/bin/bash
# Bot Router 服务管理脚本

SERVICE_DIR="/projects/tts-bot/bot-router"
NGINX_CONF="$SERVICE_DIR/conf/nginx.conf"
NGINX_PID="$SERVICE_DIR/nginx.pid"
TTYD_LOG="/projects/tts-bot/bot-router/logs/ttyd.log"

start_nginx() {
    if [ -f "$NGINX_PID" ] && kill -0 $(cat "$NGINX_PID") 2>/dev/null; then
        echo "✅ Nginx 已在运行"
    else
        nginx -c "$NGINX_CONF"
        echo "✅ Nginx 已启动"
    fi
}

stop_nginx() {
    if [ -f "$NGINX_PID" ]; then
        kill $(cat "$NGINX_PID") 2>/dev/null
        rm -f "$NGINX_PID"
        echo "✅ Nginx 已停止"
    fi
}

start_ttyd() {
    if pgrep -f "ttyd.*7680" >/dev/null; then
        echo "✅ ttyd 已在运行"
    else
        nohup ttyd -p 7680 -W -c admin:pb200898 --base-path /bot1 tmux attach-session -t kiro > "$TTYD_LOG" 2>&1 &
        echo "✅ ttyd 已启动（需认证）"
    fi
}

stop_ttyd() {
    pkill -f "ttyd.*7680"
    echo "✅ ttyd 已停止"
}

case "$1" in
    start)
        start_nginx
        start_ttyd
        ;;
    stop)
        stop_nginx
        stop_ttyd
        ;;
    restart)
        stop_nginx
        stop_ttyd
        sleep 2
        start_nginx
        start_ttyd
        ;;
    status)
        echo "=== Nginx ==="
        if [ -f "$NGINX_PID" ] && kill -0 $(cat "$NGINX_PID") 2>/dev/null; then
            echo "✅ 运行中 (PID: $(cat $NGINX_PID))"
        else
            echo "❌ 未运行"
        fi
        
        echo ""
        echo "=== ttyd ==="
        if pgrep -f "ttyd.*7680" >/dev/null; then
            echo "✅ 运行中 (PID: $(pgrep -f 'ttyd.*7680'))"
        else
            echo "❌ 未运行"
        fi
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
