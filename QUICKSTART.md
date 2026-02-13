# TTS Bot 快速指南

## 一键操作

```bash
# 启动所有服务
bash start.sh

# 检查状态
bash status.sh

# 停止所有服务
bash stop.sh
```

## 服务说明

- **Bot API** (15001端口) - 提供语音识别服务
- **Telegram Bot** - 接收消息，文字转语音
- **Handler** - 处理队列消息

## 日志位置

- Bot API: `~/logs/bot_api.log`
- Bot: `~/logs/tts_bot.log`
- Handler: `~/logs/kiro_handler.log`

## 配置

- Token: `~/data/tts-tg-bot/token.txt`
- 队列: `~/data/tts-tg-bot/queue/`

## 故障排查

```bash
# 查看日志
tail -f ~/logs/tts_bot.log

# 检查端口
netstat -tlnp | grep 15001

# 清理队列
rm ~/data/tts-tg-bot/queue/*_A.json
```
