#!/bin/bash
# Docker 容器启动脚本 - supervisor 模式
set -e
cd /root/projects/tts-bot
exec python3 scripts/supervisor.py
