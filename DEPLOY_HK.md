# TTS Bot 香港部署指南

## 步骤 1: 获取 Telegram Bot Token

Bot 已创建：
- **Bot Name**: Kiro Auto Bot
- **Username**: @kiro_auto_1770976356_bot
- **Token 位置**: `~/data/tts-tg-bot/token.txt`

**查看 Token**:
```bash
cat ~/data/tts-tg-bot/token.txt
```

## 步骤 2: 启动香港 GCP 实例

```bash
# 使用 gcloud 启动（如果有配置）
gcloud compute instances start INSTANCE_NAME --zone=asia-east2-a

# 或通过 GCP Console 手动启动
```

## 步骤 3: SSH 连接到香港实例

```bash
ssh your-hk-instance
```

## 步骤 4: 在香港实例上部署

```bash
# 1. 删除旧的 tts-bot（如果存在）
rm -rf ~/projects/tts-bot

# 2. 克隆最新代码
git clone git@github.com:cicy-dev/tts-bot.git ~/projects/tts-bot

# 3. Token 已在本地配置
# Token 位置: ~/data/tts-tg-bot/token.txt
# 无需额外配置

# 4. 一键启动
cd ~/projects/tts-bot
bash start.sh
```

## 步骤 5: 验证服务

```bash
# 检查服务状态
bash ~/projects/tts-bot/status.sh

# 查看日志
tail -f ~/logs/tts_bot.log
```

## 步骤 6: 测试 Bot

1. 在 Telegram 中找到 @tts_test_1770975065_bot
2. 发送 `/start`
3. 发送文字消息，应该收到语音回复

## 快速命令

```bash
# 一键部署（复制粘贴）
rm -rf ~/projects/tts-bot && \
git clone git@github.com:cicy-dev/tts-bot.git ~/projects/tts-bot && \
mkdir -p ~/data/tts-tg-bot && \
echo "8372241507:AAG5_2v5J5KIL51jsiC7NjRf5mGm1QAWWII" > ~/data/tts-tg-bot/token.txt && \
cd ~/projects/tts-bot && \
bash start.sh
```

## 故障排查

```bash
# 停止服务
bash ~/projects/tts-bot/stop.sh

# 查看完整日志
cat ~/logs/tts_bot.log
cat ~/logs/bot_api.log

# 重启服务
bash ~/projects/tts-bot/start.sh
```
