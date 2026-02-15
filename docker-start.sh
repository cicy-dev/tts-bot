#!/bin/bash
# Docker 容器启动脚本 - 后台服务模式
# Bot 进程由独立的 docker-compose service 运行
# 这里只跑：tmux 初始化 + ttyd + API + QA Matcher + Collector
set -e
cd /root/projects/tts-bot

# 初始化 tmux windows 和 ttyd
python3 -u scripts/init_tmux.py

# 启动 API
python3 scripts/bot_api.py &
API_PID=$!

# 启动 QA Matcher
python3 -u scripts/qa_matcher.py &
QA_PID=$!

# 启动 ttyd Collector
python3 -u scripts/ttyd_collector.py &
COL_PID=$!

echo "✅ 后台服务启动完成: API=$API_PID QA=$QA_PID Collector=$COL_PID"

# 等任意子进程退出就退出（触发 docker restart）
wait -n
