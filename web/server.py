#!/usr/bin/env python3
"""
语音聊天网页服务器
"""
from flask import Flask, request, jsonify, send_file
import subprocess
import os

app = Flask(__name__)

@app.route('/')
def index():
    return send_file('/projects/tts-bot/web/simple_voice.html')

@app.route('/upload_voice', methods=['POST'])
def upload_voice():
    """接收语音，转文字，发送到 Kiro"""
    try:
        audio = request.files['audio']
        audio_path = '/tmp/web_voice.webm'
        audio.save(audio_path)
        
        # 转换为 WAV
        wav_path = '/tmp/web_voice.wav'
        result = subprocess.run(
            ['ffmpeg', '-i', audio_path, '-ar', '16000', '-ac', '1', wav_path, '-y'], 
            capture_output=True
        )
        
        if result.returncode != 0:
            return jsonify({'error': '音频转换失败', 'text': '[转换失败]'}), 400
        
        # STT
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        
        try:
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
                text = recognizer.recognize_google(audio_data, language='zh-CN')
        except sr.UnknownValueError:
            text = '[无法识别]'
        except Exception as e:
            text = f'[识别错误: {str(e)}]'
        
        # 发送到 Kiro
        subprocess.run(['tmux', 'send-keys', '-t', 'master:0.0', text, 'Enter'])
        
        # 清理
        os.remove(audio_path)
        os.remove(wav_path)
        
        return jsonify({'text': text})
    except Exception as e:
        return jsonify({'error': str(e), 'text': '[处理失败]'}), 500

@app.route('/send_text', methods=['POST'])
def send_text():
    """接收文字，发送到 Kiro"""
    try:
        data = request.json
        text = data.get('text', '')
        
        if text:
            # 发送到 Kiro
            subprocess.run(['tmux', 'send-keys', '-t', 'master:0.0', text, 'Enter'])
            return jsonify({'status': 'ok'})
        else:
            return jsonify({'error': '空消息'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8899)
