#!/usr/bin/env python3
"""
监控 Kiro tmux 窗口，发送回复到 Telegram
"""
import subprocess
import time
import requests

TMUX_WIN_ID = "master:0.0"
BOT_TOKEN = "8170423748:AAGg93MOqQJDaf9wAsR9dIHQwS3uxRGDjt0"
CHAT_ID = "7943234085"
SENT_IDS = set()

def capture_tmux():
    """捕获 tmux 内容"""
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", TMUX_WIN_ID, "-p"],
        capture_output=True, text=True
    )
    return result.stdout

def send_telegram(text):
    """发送消息到 Telegram"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    print(f"📤 Sent: {text[:50]}", flush=True)

def main():
    print("👀 Monitoring tmux for >>> messages...")
    last_content = ""
    
    while True:
        content = capture_tmux()
        
        # 只处理新内容
        if content != last_content:
            lines = content.split('\n')
            for line in lines:
                if line.startswith(">>>"):
                    # 提取消息
                    msg = line[3:].strip()
                    msg_id = hash(msg)
                    
                    # 避免重复发送
                    if msg_id not in SENT_IDS:
                        send_telegram(msg)
                        SENT_IDS.add(msg_id)
            
            last_content = content
        
        time.sleep(2)

if __name__ == '__main__':
    main()
