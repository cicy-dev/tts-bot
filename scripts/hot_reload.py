#!/usr/bin/env python3
"""
Bot 热重载启动器
"""
import sys
import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class BotReloader(FileSystemEventHandler):
    def __init__(self):
        self.process = None
        self.start_bot()
    
    def start_bot(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
        
        print("🔄 启动 Bot...")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tts_bot.bot", "--debug"],
            cwd="/Users/ton/Desktop/vb/tts-bot"
        )
    
    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            print(f"📝 检测到文件变化: {event.src_path}")
            time.sleep(0.5)
            self.start_bot()

if __name__ == "__main__":
    reloader = BotReloader()
    observer = Observer()
    observer.schedule(reloader, "/Users/ton/Desktop/vb/tts-bot/tts_bot", recursive=True)
    observer.start()
    
    print("👀 监控文件变化中...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        if reloader.process:
            reloader.process.terminate()
    observer.join()
