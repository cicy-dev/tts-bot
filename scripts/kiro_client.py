#!/usr/bin/env python3
"""
Kiro-CLI API Client
调用 Bot API 获取消息，用 kiro-cli 处理并回复
"""

import requests
import subprocess
import time
import json

API_URL = "http://localhost:15001"

def get_messages():
    """获取待处理消息"""
    try:
        resp = requests.get(f"{API_URL}/messages", timeout=5)
        return resp.json().get('messages', [])
    except:
        return []

def send_reply(msg_id, reply_text):
    """发送回复"""
    try:
        resp = requests.post(f"{API_URL}/reply", 
                           json={'id': msg_id, 'reply': reply_text},
                           timeout=5)
        return resp.json().get('success', False)
    except:
        return False

def call_kiro(text):
    """调用 kiro-cli 获取回复"""
    try:
        result = subprocess.run(
            ['kiro-cli', 'chat', text],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except:
        return None

def main():
    print("🤖 Kiro-CLI API Client 已启动")
    print(f"📡 API: {API_URL}\n")
    
    processed = set()
    
    while True:
        try:
            messages = get_messages()
            
            for msg in messages:
                msg_id = msg['id']
                
                if msg_id in processed:
                    continue
                
                text = msg['text']
                username = msg['username']
                
                print(f"\n{'='*60}")
                print(f"📨 收到来自 @{username} 的消息:")
                print(f"💬 {text}")
                print(f"{'='*60}")
                print("🤖 正在请求 Kiro AI...")
                
                # 调用 kiro-cli
                reply = call_kiro(text)
                
                if reply:
                    print(f"✅ AI 回复: {reply[:100]}...")
                    
                    # 发送回复
                    if send_reply(msg_id, reply):
                        print("✅ 回复已发送\n")
                        processed.add(msg_id)
                    else:
                        print("❌ 发送回复失败\n")
                else:
                    print("❌ Kiro AI 调用失败\n")
            
            time.sleep(2)
            
        except KeyboardInterrupt:
            print("\n\n👋 退出中...")
            break
        except Exception as e:
            print(f"❌ 错误: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
