FROM python:3.12-slim

WORKDIR /app

# 安装依赖（包括 curl 用于健康检查）
RUN apt-get update && apt-get install -y ffmpeg curl tmux && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY tts_bot/ ./tts_bot/
COPY scripts/ ./scripts/

# 启动脚本
COPY docker-start.sh .
COPY bots.conf* ./
RUN chmod +x docker-start.sh

CMD ["./docker-start.sh"]
