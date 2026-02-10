#!/usr/bin/env python3
"""
Kiro-CLI 消息处理器
监控 TTS Bot 的消息队列，处理并回复
"""

import os
import json
import time
import subprocess

QUEUE_DIR = os.path.expanduser("~/data/tts-tg-bot/queue")

def process_message(queue_file):
    """处理单个消息"""
    try:
        with open(queue_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if data.get('status') != 'pending':
            return
        
        user_text = data['text']
        username = data.get('username', 'Unknown')
        
        print(f"\n{'='*60}")
        print(f"📨 收到来自 @{username} 的消息:")
        print(f"💬 {user_text}")
        print(f"{'='*60}\n")
        
        # 调用 kiro-cli 获取 AI 回复
        print("🤖 正在请求 Kiro AI 回复...")
        try:
            result = subprocess.run(
                ['kiro-cli', 'chat', user_text],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                reply = result.stdout.strip()
                print(f"✅ AI 回复: {reply[:100]}...\n")
            else:
                print(f"❌ Kiro 调用失败: {result.stderr}")
                reply = "抱歉，AI 处理失败，请稍后再试。"
                
        except subprocess.TimeoutExpired:
            print("⏱️ AI 响应超时")
            reply = "抱歉，AI 响应超时，请稍后再试。"
        except Exception as e:
            print(f"❌ 调用 Kiro 失败: {e}")
            reply = f"抱歉，系统错误: {str(e)}"
        
        # 保存回复
        reply_file = queue_file.replace('.json', '_reply.json')
        reply_data = {
            "reply": reply,
            "timestamp": time.time()
        }
        
        with open(reply_file, 'w', encoding='utf-8') as f:
            json.dump(reply_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 回复已发送！\n")
            
    except Exception as e:
        print(f"❌ 处理失败: {e}\n")

def main():
    """主循环"""
    print("🤖 Kiro-CLI 消息处理器已启动")
    print(f"📁 监控目录: {QUEUE_DIR}\n")
    
    processed = set()
    
    while True:
        try:
            # 扫描队列目录
            if os.path.exists(QUEUE_DIR):
                files = sorted([f for f in os.listdir(QUEUE_DIR) if f.endswith('.json') and not f.endswith('_reply.json')])
                
                for filename in files:
                    queue_file = os.path.join(QUEUE_DIR, filename)
                    
                    if queue_file not in processed:
                        process_message(queue_file)
                        processed.add(queue_file)
            
            time.sleep(2)
            
        except KeyboardInterrupt:
            print("\n\n👋 退出中...")
            break
        except Exception as e:
            print(f"❌ 错误: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
