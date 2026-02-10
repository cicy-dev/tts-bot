#!/usr/bin/env python3
"""监控 tmux 输出并回复用户"""
import subprocess
import time
import asyncio
import aiohttp
import json
import os
import re

QUEUE_DIR = os.path.expanduser("~/data/tts-tg-bot/queue")
os.makedirs(QUEUE_DIR, exist_ok=True)

# 已发送的回复记录（用索引标记位置）
last_reply_index = -1
sent_requests = []  # 记录已发送的请求

def get_capture():
    """获取当前 capture-pane 内容"""
    result = subprocess.run(
        ['tmux', 'capture-pane', '-t', '6:master.0', '-p'],
        capture_output=True, text=True
    )
    return result.stdout

def extract_replies(content):
    """提取所有回复段落（用 Credits: 分隔）"""
    # 按 Credits: 分隔
    parts = content.split('Credits:')
    
    replies = []
    for i, part in enumerate(parts[:-1]):  # 最后一段可能未完成
        lines = part.strip().split('\n')
        
        # 找到用户输入（以 > 开头）
        user_input = None
        reply_lines = []
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('>') and not stripped.startswith('> What'):
                # 这是用户输入
                user_input = stripped[1:].strip()
            elif 'Thinking' not in line and stripped and not stripped.startswith('>'):
                # 这是回复内容
                reply_lines.append(stripped)
        
        if reply_lines:
            reply_text = '\n'.join(reply_lines)
            replies.append({
                'index': i,
                'user_input': user_input,
                'reply': reply_text
            })
    
    return replies

def is_thinking():
    """检查是否在 Thinking 状态"""
    content = get_capture()
    lines = content.strip().split('\n')
    last_line = lines[-1] if lines else ""
    return 'Thinking' in last_line

async def send_reply(chat_id, text, full_text=None):
    """发送回复到 Telegram"""
    async with aiohttp.ClientSession() as session:
        async with session.post('http://localhost:15001/reply', json={
            'chat_id': chat_id,
            'reply': text,
            'full_text': full_text,
            'message_id': ''
        }) as resp:
            return await resp.json()

async def process_queue():
    """处理队列"""
    global last_reply_index, sent_requests
    last_capture = ""
    
    while True:
        try:
            files = sorted([f for f in os.listdir(QUEUE_DIR) if f.endswith('.json')])
            
            if not files:
                await asyncio.sleep(0.5)
                continue
            
            # 处理第一条消息
            first_file = files[0]
            filepath = os.path.join(QUEUE_DIR, first_file)
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            chat_id = data['chat_id']
            user_text = data['text']
            sent_requests.append(user_text)
            
            print(f"处理请求: {user_text[:30]}")
            
            # 等待 Thinking 开始
            await asyncio.sleep(2)
            
            # 等待 Thinking 结束
            while is_thinking():
                await asyncio.sleep(1)
            
            print("Thinking 结束，等待稳定")
            
            # 等待内容稳定
            stable_count = 0
            while stable_count < 2:
                current_capture = get_capture()
                if current_capture == last_capture:
                    stable_count += 1
                else:
                    stable_count = 0
                    last_capture = current_capture
                await asyncio.sleep(1)
            
            print("分析回复")
            
            # 提取所有回复
            all_replies = extract_replies(get_capture())
            
            # 找出新回复（index > last_reply_index 且不是用户请求）
            for reply_obj in all_replies:
                if reply_obj['index'] > last_reply_index:
                    reply_text = reply_obj['reply']
                    user_input = reply_obj['user_input']
                    
                    # 跳过用户自己的请求
                    if user_input and user_input in sent_requests:
                        print(f"跳过请求: {user_input[:30]}")
                        last_reply_index = reply_obj['index']
                        continue
                    
                    # 发送回复
                    if len(reply_text) > 50:
                        short = reply_text[:50] + "..."
                        await send_reply(chat_id, short, reply_text)
                        print(f"✓ 回复: {short}")
                    else:
                        await send_reply(chat_id, reply_text)
                        print(f"✓ 回复: {reply_text[:50]}")
                    
                    last_reply_index = reply_obj['index']
            
            os.remove(filepath)
            
            # 处理剩余消息
            remaining_files = sorted([f for f in os.listdir(QUEUE_DIR) if f.endswith('.json')])
            if remaining_files:
                texts = []
                for f in remaining_files:
                    fp = os.path.join(QUEUE_DIR, f)
                    with open(fp, 'r') as file:
                        d = json.load(file)
                        texts.append(d['text'])
                        sent_requests.append(d['text'])
                    os.remove(fp)
                
                combined = '\n'.join(texts)
                subprocess.run(['tmux', 'send-keys', '-t', '6:master.0', combined])
                await asyncio.sleep(1)
                subprocess.run(['tmux', 'send-keys', '-t', '6:master.0', 'Enter'])
                print(f"批量发送: {len(texts)} 条")
        
        except Exception as e:
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()
        
        await asyncio.sleep(0.5)

if __name__ == '__main__':
    print("🔍 监控启动")
    asyncio.run(process_queue())
