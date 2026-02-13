#!/bin/bash
# Docker 容器启动脚本 - 文件变化自动重载

set -e

start_all() {
  echo "🚀 启动所有服务..."
  python3 scripts/bot_api.py > /tmp/bot_api.log 2>&1 &
  echo $! > /tmp/api.pid
  sleep 2
  python3 -m tts_bot.bot > /tmp/bot.log 2>&1 &
  echo $! > /tmp/bot.pid
  python3 -u scripts/kiro_handler.py > /tmp/handler.log 2>&1 &
  echo $! > /tmp/handler.pid
  echo "✅ 所有服务已启动 (API=$(cat /tmp/api.pid) Bot=$(cat /tmp/bot.pid) Handler=$(cat /tmp/handler.pid))"
}

kill_all() {
  for f in /tmp/api.pid /tmp/bot.pid /tmp/handler.pid; do
    [ -f "$f" ] && kill $(cat "$f") 2>/dev/null || true
  done
  sleep 1
}

start_all

# 监听文件变化 + 进程守护
watchmedo shell-command \
  --patterns="*.py" \
  --recursive \
  --command='echo "🔄 $(date +%H:%M:%S) 检测到代码变化: ${watch_src_path}, 重载中..."' \
  --drop \
  tts_bot/ scripts/ &
WATCH_PID=$!

# 主循环：检测文件变化触发重载 + 进程守护
LAST_HASH=$(find tts_bot/ scripts/ -name "*.py" -exec md5sum {} + | sort | md5sum)

while true; do
  CUR_HASH=$(find tts_bot/ scripts/ -name "*.py" -exec md5sum {} + | sort | md5sum)
  if [ "$CUR_HASH" != "$LAST_HASH" ]; then
    echo "🔄 $(date '+%H:%M:%S') 代码变化，重载所有服务..."
    kill_all
    start_all
    LAST_HASH=$CUR_HASH
  fi

  # 进程守护
  for pair in "api.pid:python3 scripts/bot_api.py:/tmp/bot_api.log" \
              "bot.pid:python3 -m tts_bot.bot:/tmp/bot.log" \
              "handler.pid:python3 -u scripts/kiro_handler.py:/tmp/handler.log"; do
    IFS=: read -r pf cmd logf <<< "$pair"
    if [ -f "/tmp/$pf" ] && ! kill -0 $(cat "/tmp/$pf") 2>/dev/null; then
      echo "⚠️ $(date '+%H:%M:%S') 进程崩溃，重启: $cmd"
      $cmd > "$logf" 2>&1 &
      echo $! > "/tmp/$pf"
    fi
  done

  sleep 3
done
