#!/usr/bin/env python3
"""
语音识别 API 服务
接收音频文件，返回识别的文字
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import speech_recognition as sr
from pydub import AudioSegment
import os
import uvicorn

app = FastAPI()

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post('/stt')
async def speech_to_text(audio: UploadFile = File(...)):
    """语音转文字"""
    try:
        # 保存音频
        temp_path = f"/tmp/{audio.filename}"
        with open(temp_path, 'wb') as f:
            content = await audio.read()
            f.write(content)
        
        # 转换为 WAV
        audio_segment = AudioSegment.from_file(temp_path)
        wav_path = "/tmp/temp_audio.wav"
        audio_segment.export(wav_path, format='wav')
        
        # 识别
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            try:
                text = recognizer.recognize_google(audio_data, language='zh-CN')
            except:
                try:
                    text = recognizer.recognize_google(audio_data, language='en-US')
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"识别失败: {str(e)}")
        
        # 清理
        os.remove(temp_path)
        os.remove(wav_path)
        
        return {'text': text, 'success': True}
    
    except Exception as e:
        return {'error': str(e), 'success': False}

@app.get('/health')
def health():
    return {'status': 'ok'}

if __name__ == '__main__':
    print("🎤 语音识别 API 启动: http://0.0.0.0:8000")
    uvicorn.run(app, host='0.0.0.0', port=8000)
