# TTS Bot 架构文档

## 架构概览

```
TG 用户 → Telegram Bot API → bot.py → tmux send_msg → kiro-cli 处理
                                         ↓
                                    MySQL qa_pair (记录 Q)
                                         ↓
用户通过 ttyd 查看 kiro-cli 输出 ← ttyd_collector → MySQL terminal_snapshot
                                         ↓
                                    qa_matcher → 匹配 Q&A (RAG 用)
```

## 核心流程

1. 用户在 Telegram 发消息
2. `bot.py` 收到消息，直接通过 tmux send_msg 发送到 kiro-cli（像真人打字）
3. kiro-cli 在 tmux 中处理并输出回复
4. 用户通过 ttyd web terminal 查看 kiro-cli 的实时输出
5. `qa_matcher.py` 后台从 terminal_snapshot 提取回复，写入 qa_pair 表（供未来 RAG 使用）

## 目录结构

```
tts-bot/
├── docker-compose.yml      # Docker 配置
├── Dockerfile              # 镜像构建
├── requirements.txt        # Python 依赖
├── .env                    # 环境变量（token 等）
├── bot-router/             # Node.js ttyd 路由（运行在宿主机）
│   ├── service.sh          # 启动脚本
│   └── package.json
├── scripts/                # 后台服务脚本
│   ├── supervisor.py       # 进程管理：启动 bot + ttyd + qa_matcher + api
│   ├── bot_api.py          # HTTP API（健康检查、消息查询、回复发送）
│   ├── qa_matcher.py       # QA 匹配：从终端快照提取回复 → MySQL qa_pair
│   └── ttyd_collector.py   # 终端采集：ttyd WebSocket → MySQL terminal_snapshot
├── tts_bot/                # Bot 核心代码
│   ├── bot.py              # Telegram Bot 主逻辑
│   ├── config.py           # 配置
│   ├── session_map.py      # MySQL bot_config 封装
│   ├── tmux_backend.py     # tmux 操作基类
│   ├── kiro_tmux_backend.py # kiro-cli tmux 操作
│   ├── stt_backend.py      # STT 接口
│   └── default_stt.py      # 默认 STT 实现
└── data/                   # 运行时数据
    └── logs/               # 日志
```

## MySQL 表

| 表名 | 用途 |
|------|------|
| `bot_config` | Bot 配置（token、tmux session、ttyd 端口等） |
| `terminal_snapshot` | 终端快照（ttyd_collector 写入） |
| `qa_pair` | 问答对（bot.py 写 Q，qa_matcher 写 A，RAG 用） |
| `global_vars` | 全局键值存储 |

## 进程管理

`supervisor.py` 负责启动和守护：
- 每个 bot 的 `tts_bot.bot` 进程
- 每个 bot 的 `ttyd` 实例
- `bot_api.py` HTTP API
- `qa_matcher.py` QA 匹配

## 端口

| 端口 | 服务 |
|------|------|
| 12345 | Node.js Bot Router（宿主机） |
| 15001 | bot_api.py HTTP API |
| 16000-16002 | ttyd（master/auth/worker） |
