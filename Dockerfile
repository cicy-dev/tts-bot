FROM python:3.12-slim

WORKDIR /root/projects/tts-bot

# 安装依赖（包括 curl 用于健康检查）
RUN apt-get update && apt-get install -y ffmpeg curl tmux nginx && rm -rf /var/lib/apt/lists/* \
    && curl -sL https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 -o /usr/local/bin/ttyd \
    && chmod +x /usr/local/bin/ttyd

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

CMD ["bash", "docker-start.sh"]
