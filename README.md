# W3C TTS Bot

Telegram 文字转语音机器人

## 功能特性

- ✅ 文字转语音（中英文支持）
- ✅ 使用微软 Edge TTS（免费）
- ✅ 多种语音选择
- ✅ 自动语音回复

## 项目结构

```
tts-bot/
├── tts_bot/          # 核心代码
│   ├── __init__.py
│   └── bot.py
├── scripts/          # 工具脚本
│   ├── bot_api.py
│   ├── kiro_client.py
│   ├── kiro_handler.py
│   └── hot_reload.py
├── tests/            # 测试
│   ├── test_bot.py
│   └── test_integration.py
├── logs/             # 日志文件
├── setup.py
├── pyproject.toml
└── requirements.txt
```

## 快速开始

### 1. 安装

```bash
pip install tts-tg-bot
```

或从源码安装：

```bash
git clone <repo>
cd tts-bot
pip install -e .
```

### 2. 配置 Token

创建 `token.txt` 文件，写入你的 Telegram Bot Token：

```bash
echo "YOUR_BOT_TOKEN" > token.txt
```

### 3. 启动 Bot

```bash
tts-tg-bot
```

或使用 Python 模块：

```bash
python -m tts_bot.bot
```

## 使用方法

1. 在 Telegram 搜索 `@w3c_tts_bot`
2. 发送 `/start` 查看帮助
3. 发送任何文字，Bot 会返回语音
4. 使用 `/voice` 命令切换语音

## 支持的语音

- 中文女声：zh-CN-XiaoxiaoNeural（默认）
- 中文男声：zh-CN-YunxiNeural
- 英文女声：en-US-JennyNeural
- 英文男声：en-US-GuyNeural

## 开发

### 运行测试

```bash
pytest tests/ -v
```

### 发布

```bash
./scripts/publish.sh
```

## 技术栈

- Python 3.8+
- python-telegram-bot - Telegram Bot API
- edge-tts - 微软免费 TTS 服务

## Bot 信息

- Bot 名称: W3C TTS Bot
- Username: @w3c_tts_bot

## 开发者

TTS Bot 开发战士 ⚔️
# tts-bot
