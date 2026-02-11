# 语音识别 API

## 启动服务

```bash
cd /Users/ton/Desktop/tts-bot
pip install fastapi uvicorn speechrecognition pydub
python stt_api.py
```

服务运行在: `http://localhost:8000`

## API 接口

**POST /stt**
- 接收音频文件
- 返回识别的文字

**GET /health**
- 健康检查

## Flutter 配置

修改 `/Users/ton/Desktop/voice_app/lib/main.dart` 第 42 行：
```dart
Uri.parse('http://YOUR_SERVER_IP:8000/stt')
```

替换 `YOUR_SERVER_IP` 为你的服务器 IP
