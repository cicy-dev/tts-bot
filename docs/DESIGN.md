# TTS Bot 双队列改进方案

## 一、需求文档

### 1.1 项目背景

TTS Bot 是一个 Telegram 文字转语音机器人，目前支持语音识别、发送给 Kiro AI 处理、接收回复并发送给用户。但当前存在以下问题：

- 消息顺序无法保证，A/B 消息可能错位
- tmux 中历史消息丢失，导致回复对应关系混乱
- 无队列机制，多条消息并发时处理混乱
- 无用户反馈机制，处理状态不清晰
- 无法处理 Kiro "Thinking" 状态

### 1.2 功能需求

| 编号 | 功能 | 描述 | 优先级 |
|------|------|------|--------|
| FR-01 | ACK 消息机制 | 用户发送语音后 Bot 发送状态消息 | P0 |
| FR-02 | A队列机制 | 用户发送消息后立即进入 A 队列 | P0 |
| FR-03 | ACK 消息编辑 | 识别完成→编辑为"处理中" | P0 |
| FR-04 | ACK 消息删除 | Kiro 回复后删除 ACK 消息 | P0 |
| FR-05 | B队列机制 | Kiro 回复后进入 B 队列，按顺序发送给用户 | P0 |
| FR-06 | 顺序处理 | A队列按时间顺序发送到 tmux | P0 |
| FR-07 | 顺序处理 | B队列按时间顺序发送给用户 | P0 |
| FR-08 | Thinking 检测 | 检测 Kiro "Thinking" 状态 | P0 |
| FR-09 | t/n/y 决策 | 用户可决策是否继续等待 | P0 |
| FR-10 | t/n/y 配置 | t/n/y 可配置哪些字符触发直接发送 | P1 |
| FR-11 | 特殊命令 | /LEFT /RIGHT /UP /DOWN 直接发送给 tmux | P1 |
| FR-12 | 错误处理 | 网络/TOKEN 错误时添加删除按钮 | P1 |
| FR-13 | 文本处理 | 文本消息跳过 STT 直接进队列 | P1 |
| FR-14 | tmux 发送规则 | 发送消息→sleep 1s→ENTER | P0 |
| FR-15 | /capture 命令 | 捕获 tmux pane 内容，格式化为代码块发送给用户 | P1 |
| FR-16 | /tree 命令 | 树状显示所有 tmux session、window、pane | P1 |
| FR-17 | /resize-pane 命令 | 设置当前窗格高度 | P1 |
| FR-18 | /win_id 命令 | 获取当前配置的 win_id | P1 |
| FR-19 | /win_id_set 命令 | 设置当前 win_id，保存到本地配置 | P1 |
| FR-20 | /pane_height 命令 | 返回当前窗格高度行数 | P1 |
| FR-21 | /cut_max_rows 命令 | 获取最大截取行数 | P1 |
| FR-22 | /cut_rows_set 命令 | 设置最大行数，保存到本地配置 | P1 |
| FR-23 | /new_win 命令 | 创建新窗口，默认执行 init_code | P1 |
| FR-24 | /del_win 命令 | 删除指定窗口 | P1 |

### 1.3 非功能需求

| 编号 | 需求 | 描述 |
|------|------|------|
| NFR-01 | 可靠性 | 消息不丢失，处理完成后清理 |
| NFR-02 | 顺序保证 | A队列和B队列各自严格按时间顺序 |
| NFR-03 | 简单性 | 保持现有架构，尽量少的改动 |
| NFR-04 | 可观测 | 关键步骤有日志输出 |

### 1.4 输入输出

**输入**：
- 用户 Telegram 语音消息
- 用户 Telegram 文字消息
- 用户 t/n/y 决策消息
- 用户 /LEFT /RIGHT /UP /DOWN 命令
- 用户 /capture 命令
- 用户 /tree, /resize-pane, /win_id, /win_id_set, /pane_height, /cut_max_rows, /cut_rows_set, /new_win, /del_win 命令

**输出**：
- A队列文件：`msg_{timestamp}_{message_id}_A.json`
- B队列文件：`msg_{timestamp}_{message_id}_B_reply.json`
- ACK 消息：🎧识别中 → ⚙️处理中 → ⚠️回复失败(带删除按钮)
- 最终回复：按顺序发送给用户的 Kiro 回复

### 1.5 约束条件

- 单用户场景
- 继续使用 tmux 6:master.0 与 Kiro 交互
- 使用文件队列（JSON格式）
- Python 3.8+

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Telegram User                            │
│                           (单用户)                               │
└─────────────────────────────┬───────────────────────────────────┘
                              │ 发送语音/文字/t/n/y/命令
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      tts_bot/bot.py                              │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ handle_voice() / handle_message()                           │ │
│  │                                                             │ │
│  │ 1. 判断消息类型:                                             │ │
│  │    ├─ t/n/y (在配置中): 跳过队列，直接发送                   │ │
│  │    ├─ 特殊命令(/LEFT/RIGHT/UP/DOWN): 直接发送给 tmux       │ │
│  │    └─ 普通消息:                                             │ │
│  │        ├─ 创建 A 队列文件                                   │ │
│  │        ├─ 发送 ACK 消息                                     │ │
│  │        ├─ 执行语音识别 (如需要)                             │ │
│  │        └─ 更新 A 队列文件                                   │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              │ A队列就绪 + ACK消息已创建
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    scripts/kiro_handler.py                       │
│  ┌─────────────────────┐    ┌─────────────────────┐            │
│  │    A队列处理器       │    │    B队列处理器       │            │
│  │                     │    │                     │            │
│  │ - 按时间顺序扫描     │    │ - 按时间顺序扫描     │            │
│  │ - 检查 tmux Thinking │    │ - 删除对应 ACK 消息  │            │
│  │ - 发送到 tmux        │    │ - 发送给用户        │            │
│  │ - t/n/y 决策处理     │    │ - 更新 status        │            │
│  │ - 更新 status        │    │                     │            │
│  └──────────┬──────────┘    └──────────┬──────────┘            │
│             │                          │                       │
│             ▼                          ▼                       │
│  ┌─────────────────────┐    ┌─────────────────────┐            │
│  │  tmux 6:master.0    │    │    Telegram Bot     │            │
│  │                     │    │                     │            │
│  │  Kiro AI 处理       │    │  - 删除 ACK 消息    │            │
│  │  Thinking 检测       │    │  - 发送 Kiro 回复   │            │
│  └──────────┬──────────┘    └─────────────────────┘            │
│             │                                                 │
│             │ Kiro 回复                                         │
│             ▼                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ B队列生成 (待确认实现方式)                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 ACK 消息状态

| 状态 | 显示 | 触发条件 |
|------|------|----------|
| 识别中 | 🎧 识别中 | 语音识别中 |
| 处理中 | ⚙️ 处理中 | 识别完成，等待发送 tmux |
| 识别失败 | ❌ 识别失败 | 语音识别失败 |
| 回复失败 | ⚠️ 回复失败 | 网络/TOKEN 错误（带删除按钮） |

### 2.3 t/n/y 决策配置

```python
# 配置项 - 可自定义哪些字符触发直接发送
TNY_DECISION_CHARS = ['t', 'n', 'y']  # 默认全部启用

# t/n/y 含义
# t = trust (信任) → 跳过队列，直接发送
# n = no (否) → 清空未发送队列，删除 ACK
# y = yes (是) → 跳过队列，直接发送
```

### 2.4 特殊命令（直接发送给 tmux）

| 命令 | 含义 |
|------|------|
| `/LEFT` | tmux 发送左箭头 |
| `/RIGHT` | tmux 发送右箭头 |
| `/UP` | tmux 发送上箭头 |
| `/DOWN` | tmux 发送下箭头 |
| `/capture` | 捕获 tmux pane 内容，发送给用户 |

### 2.5 tmux 配置

```python
# tmux 配置
TMUX_SESSION = "6:master.0"  # 默认 tmux 目标 win_id
CAPTURE_MAX_ROWS = None  # 捕获行数限制，None=默认50行
INIT_CODE = "kiro-cli"  # 新窗口默认执行命令

# 本地配置存储路径
CONFIG_PATH = "~/.tts-bot/config.json"
```

### 2.6 tmux 管理命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `/tree` | 树状显示所有 session、window、pane | /tree |
| `/resize-pane <高度>` | 设置当前窗格高度 | /resize-pane 100 |
| `/win_id` | 获取当前配置的 win_id | /win_id |
| `/win_id_set <win_id>` | 设置当前 win_id | /win_id_set 6:master.0 |
| `/pane_height` | 返回当前窗格高度行数 | /pane_height |
| `/cut_max_rows` | 获取最大截取行数 | /cut_max_rows |
| `/cut_rows_set <行数>` | 设置最大行数 | /cut_rows_set 100 |
| `/new_win <session> <window> [command]` | 创建新窗口 | /new_win bot api kiro-cli |
| `/del_win <win_id>` | 删除窗口 | /del_win 6:master.0 |

### 2.7 tmux 发送规则

```
发送到 tmux:
1. 发送消息文本
2. sleep 1秒
3. 发送 ENTER

发送前检查:
- tmux capture pane 检查最后一行
- 如果包含 "Thinking":
  ├─ 更新 ACK: "⏱️ Kiro 思考中, 发送 t/n/y 决策"
  ├─ t → 跳过队列，直接发送
  ├─ n → 清空未发送队列，删除 ACK
  └─ y → 跳过队列，直接发送
```

### 2.8 /capture 命令

```
用户发送 /capture:
1. 捕获 tmux pane 全部内容
2. 判断行数:
   ├─ ≤CAPTURE_MAX_ROWS 行 → 全发
   └─ >CAPTURE_MAX_ROWS 行 → 截取末尾 CAPTURE_MAX_ROWS 行
3. 格式化为代码块发送给用户
```

### 2.9 tmux 管理命令

#### 2.9.1 /tree 命令
```
用户发送 /tree:
1. 树状显示所有 tmux session、window、pane
2. 最后一级显示 session:window.pane 格式 ID，方便复制

示例输出:
├── 6
│   └── 0 master
│       └── 6:master.0 zsh
├── al
│   ├── 0 bot
│   │   └── al:bot.0 Python
```

#### 2.9.2 /resize-pane 命令
```
用户发送 /resize-pane <高度>:
1. 设置当前窗格高度为指定行数
2. 成功发送确认消息
3. 失败发送错误消息

示例: /resize-pane 100
```

#### 2.9.3 /win_id 命令
```
用户发送 /win_id:
1. 返回当前配置的 win_id
2. 格式化为代码块发送

示例输出:
当前 win_id: 6:master.0
```

#### 2.9.4 /win_id_set 命令
```
用户发送 /win_id_set <win_id>:
1. 设置当前 win_id
2. 保存到本地配置文件
3. 返回确认消息

示例: /win_id_set 6:master.0
```

#### 2.9.5 /pane_height 命令
```
用户发送 /pane_height:
1. 返回当前窗格高度行数
2. 格式化为代码块发送
```

#### 2.9.6 /cut_max_rows 命令
```
用户发送 /cut_max_rows:
1. 返回最大截取行数
2. 格式化为代码块发送
```

#### 2.9.7 /cut_rows_set 命令
```
用户发送 /cut_rows_set <行数>:
1. 设置最大截取行数
2. 保存到本地配置文件
3. 返回确认消息

示例: /cut_rows_set 100
```

#### 2.9.8 /new_win 命令
```
用户发送 /new_win <session> <window> [command]:
1. 在指定 session 下创建新窗口
2. 默认执行 INIT_CODE ("kiro-cli")
3. 成功后发送成功消息，并切换当前 win_id 到新窗口

示例: /new_win bot api kiro-cli
```

#### 2.9.9 /del_win 命令
```
用户发送 /del_win <win_id>:
1. 直接删除指定窗口及其所有 pane
2. 删除后使用兄弟窗口的 win_id
3. 成功发送确认消息
4. win_id 不存在时发送错误消息

示例: /del_win 6:master.0
```

### 2.10 本地配置存储

```python
# ~/.tts-bot/config.json
{
  "win_id": "6:master.0",  # 当前配置的 win_id
  "cut_max_rows": 50,  # 最大截取行数
  "init_code": "kiro-cli"  # 新窗口默认执行命令
}

# 配置操作
- win_id_set: 更新 win_id，保存到配置文件
- cut_rows_set: 更新 cut_max_rows，保存到配置文件
- init_code: 固定值，不可修改
```

### 2.11 数据模型

```
用户发送 /capture:
1. 捕获 tmux pane 全部内容
2. 判断行数:
   ├─ ≤CAPTURE_MAX_ROWS 行 → 全发
   └─ >CAPTURE_MAX_ROWS 行 → 截取末尾 CAPTURE_MAX_ROWS 行
3. 格式化为代码块发送给用户
```

### 2.9 数据模型

#### A队列文件格式
```json
{
  "timestamp": 1707623000,
  "message_id": 12345,
  "ack_message_id": 123,
  "chat_id": 7943234085,
  "user_id": 7943234085,
  "text": "用户消息内容",
  "is_text": false,
  "is_tny": false,
  "status": "pending | ready | sent_to_tmux | error",
  "created_at": "2024-02-11T10:00:00Z",
  "updated_at": "2024-02-11T10:00:01Z",
  "error_count": 0,
  "error_message": null
}
```

#### B队列文件格式
```json
{
  "timestamp": 1707623000,
  "message_id": 12345,
  "ack_message_id": 123,
  "chat_id": 7943234085,
  "reply": "Kiro AI 回复内容",
  "status": "pending | ready | sent_to_user | error",
  "created_at": "2024-02-11T10:00:05Z",
  "updated_at": "2024-02-11T10:00:06Z",
  "error_count": 0
}
```

#### 状态流转

```
A队列: pending → ready → sent_to_tmux → (删除)
B队列: pending → ready → sent_to_user → (删除)

ACK消息: 🎧识别中 → ⚙️处理中 → (删除 或 ⚠️回复失败+删除按钮)
```

### 2.7 组件职责

| 组件 | 职责 |
|------|------|
| `bot.py` | 接收消息，创建 A 队列，发送/编辑 ACK 消息，执行 STT，处理 t/n/y/特殊命令 |
| `kiro_handler.py` | A队列发送到 tmux，B队列发送给用户，删除 ACK 消息，Thinking 检测 |
| `bot_api.py` | 语音识别 API (`/voice_to_text`)，可能需要调整 B队列生成逻辑 |
| `queue/` | 存储 A/B 队列文件 |

### 2.8 关键流程

#### 流程1：用户发送消息 → 判断类型
```
用户发送消息:
├─ t/n/y (在配置中):
│   └─ 跳过队列，直接发送给 tmux
├─ 特殊命令(/LEFT/RIGHT/UP/DOWN):
│   └─ 直接发送给 tmux
└─ 普通消息:
    ├─ 语音:
    │   ├─ 创建 A 队列文件 (status=pending)
    │   ├─ 发送 ACK 消息 🎧识别中
    │   ├─ 执行语音识别
    │   ├─ 成功: 编辑 ACK 为 ⚙️处理中，更新 A队列 (status=ready)
    │   └─ 失败: 编辑 ACK 为 ❌识别失败，添加删除按钮
    └─ 文本:
        ├─ 创建 A 队列文件 (status=pending, is_text=true)
        ├─ 发送 ACK 消息 ⚙️处理中
        └─ 更新 A 队列 (status=ready)
```

#### 流程2：A队列 → tmux 发送
```
1. kiro_handler 扫描 A队列 (按 timestamp 排序)
2. status=ready 的依次处理:
   ├─ 检查 tmux capture pane 最后一行
   │   ├─ 包含 "Thinking":
   │   │   └─ 更新 ACK: "⏱️ Kiro 思考中, 发送 t/n/y 决策"
   │   │       ├─ t (trust): 跳过队列，直接发送
   │   │       ├─ n (no): 清空未发送队列，删除 ACK
   │   │       └─ y (yes): 跳过队列，直接发送
   │   │
   │   └─ 无 "Thinking":
   │       ├─ 发送消息文本
   │       ├─ sleep 1s
   │       └─ 发送 ENTER
   │
   └─ 更新 status=sent_to_tmux
```

#### 流程3：Kiro 回复 → B队列
```
待确认实现方式：
- 方案A: bot_api.py 监听 kiro-cli 输出，创建 B队列
- 方案B: kiro_handler 轮询 tmux 窗口内容，提取回复
- 方案C: 其他
```

#### 流程4：B队列 → 用户
```
1. kiro_handler 扫描 B队列 (按 timestamp 排序)
2. status=ready 的依次处理:
   ├─ 删除对应的 ACK 消息 (ack_message_id)
   ├─ 发送给用户
   └─ 更新 status=sent_to_user
3. 清理已处理文件
```

#### 流程5：错误处理（网络/TOKEN 问题）
```
1. 检测到网络/TOKEN 错误
2. 编辑 ACK 消息: "⚠️ 回复失败"
3. 添加 "删除" 按钮
4. 用户自己删除消息
```

### 2.9 文件结构

```
tts-bot/
├── tts_bot/
│   ├── __init__.py
│   └── bot.py              # 修改: handle_voice/handle_message + ACK机制 + t/n/y处理
├── scripts/
│   ├── bot_api.py         # 可能需要调整 B队列生成逻辑
│   ├── kiro_handler.py    # 重写: 双队列模式 + Thinking检测 + t/n/y决策
│   └── ...
├── tests/
│   ├── test_queue.py      # 新增: 队列测试
│   ├── test_bot.py
│   └── test_integration.py
├── data/tts-tg-bot/       # 用户数据目录
│   ├── token.txt
│   ├── logs/
│   └── queue/             # A/B 队列文件存储
│       ├── msg_1707623000_12345_A.json
│       ├── msg_1707623000_12345_B_reply.json
│       └── ...
├── docs/                  # 文档目录
│   └── DESIGN.md
└── README.md
```

### 2.10 可扩展性设计

#### 2.10.1 tmux Capture 抽象接口

```python
# 抽象 tmux capture 接口
class TmuxBackend(ABC):
    """tmux 后端抽象接口"""
    
    @abstractmethod
    def send_text(self, text: str) -> bool:
        """发送文本到 tmux"""
        pass
    
    @abstractmethod
    def send_keys(self, keys: str) -> bool:
        """发送特殊按键到 tmux"""
        pass
    
    @abstractmethod
    def capture_pane(self, max_rows: Optional[int] = None) -> str:
        """捕获 tmux pane 内容
        
        Args:
            max_rows: 最大行数限制，None=默认50行
            
        Returns:
            tmux pane 内容
        """
        pass
    
    @abstractmethod
    def check_thinking(self) -> bool:
        """检测 AI 是否处于 Thinking 状态"""
        pass

# 具体实现
class KiroTmuxBackend(TmuxBackend):
    """Kiro tmux 后端实现"""
    
    TMUX_SESSION = "6:master.0"  # 可配置
    CAPTURE_MAX_ROWS = None  # 默认50行，可配置
    
    def send_text(self, text: str) -> bool:
        # 发送到 tmux
        pass
    
    def send_keys(self, keys: str) -> bool:
        # 发送特殊按键
        pass
    
    def capture_pane(self, max_rows: Optional[int] = None) -> str:
        # 捕获 tmux pane
        # 如果超过 max_rows，截取末尾行
        pass
    
    def check_thinking(self) -> bool:
        # 检查最后一行是否包含 "Thinking"
        pass
```

#### 2.10.2 AI 后端扩展（待实现）

当前实现 Kiro，通过 tmux 交互。未来可扩展支持 OpenCode 等其他 AI 后端。

**核心差异点**

| 差异点 | Kiro | OpenCode |
|--------|------|----------|
| Thinking 检测 | tmux 最后一行包含 "Thinking" | 待实现 |
| 回复提取 | tmux capture pane | 待实现 |
| 消息格式 | 普通文本 | 待实现 |

**抽象接口设计**

```python
class AIBackend(ABC):
    """AI 后端抽象接口"""
    
    @abstractmethod
    def check_thinking(self) -> bool:
        """检测 AI 是否处于 Thinking 状态"""
        pass
    
    @abstractmethod
    def extract_reply(self) -> str:
        """提取 AI 回复（分隔 Thinking 和正式回答）"""
        pass
    
    @abstractmethod
    def send_message(self, text: str) -> bool:
        """发送消息到 AI"""
        pass

class KiroAIBackend(AIBackend):
    """Kiro AI 后端实现"""
    pass

class OpenCodeAIBackend(AIBackend):
    """OpenCode AI 后端实现（待实现）"""
    pass

# 配置
AI_BACKEND = "kiro"  # 可切换为 "opencode"
```

#### 2.10.3 STT 接口扩展（待实现）

当前使用默认语音识别 API，未来可扩展支持多种 STT 服务。

**抽象接口设计**

```python
class STTBackend(ABC):
    """语音识别后端抽象接口"""
    
    @abstractmethod
    def recognize(self, audio_path: str) -> str:
        """将音频文件识别为文字"""
        pass

class DefaultSTTBackend(STTBackend):
    """默认 STT 实现"""
    pass

class OpenAIWhisperBackend(STTBackend):
    """OpenAI Whisper API 实现（待实现）"""
    pass

class BaiduSTTBackend(STTBackend):
    """百度语音识别实现（待实现）"""
    pass

# 配置
STT_BACKEND = "default"  # 可切换为 "whisper", "baidu"
```

#### 2.10.4 配置管理

```python
# config.py - 统一配置
class Config:
    # tmux 配置
    TMUX_SESSION = "6:master.0"
    CAPTURE_MAX_ROWS = None  # None=默认50行
    
    # AI 后端配置
    AI_PROVIDER = "kiro"  # kiro, opencode
    
    # STT 配置
    STT_PROVIDER = "default"  # default, whisper, baidu
    
    # t/n/y 决策配置
    TNY_DECISION_CHARS = ['t', 'n', 'y']
    
    # tmux 发送配置
    TMUX_SEND_DELAY = 1.0  # 秒
```

---

## 三、测试标准

### 3.1 测试策略

| 测试类型 | 范围 | 工具 |
|----------|------|------|
| 单元测试 | bot.py, kiro_handler.py 核心函数 | pytest + unittest.mock |
| 集成测试 | 队列完整流程 | pytest + 临时目录 |
| 手动测试 | 端到端消息处理 | Telegram 实测 |

### 3.2 测试用例

#### TC-01: ACK 消息创建和编辑
| 项目 | 内容 |
|------|------|
| 用例名称 | 发送语音后创建 ACK 消息并编辑 |
| 前置条件 | 用户发送语音消息 |
| 测试步骤 | 1. 发送语音 2. 检查 ACK 消息 🎧识别中 3. 识别完成后检查编辑为 ⚙️处理中 |
| 预期结果 | ACK 消息正确创建和编辑 |

#### TC-02: 文本消息处理
| 项目 | 内容 |
|------|------|
| 用例名称 | 文本消息跳过 STT 直接进队列 |
| 前置条件 | 用户发送文本消息 |
| 测试步骤 | 1. 发送文本 2. 检查 ACK 消息 ⚙️处理中 3. 检查 A队列 is_text=true |
| 预期结果 | 跳过 STT，直接进入 A 队列 |

#### TC-03: t/n/y 直接发送
| 项目 | 内容 |
|------|------|
| 用例名称 | t/n/y 消息跳过队列直接发送 |
| 前置条件 | 用户发送 t/n/y 字符 |
| 测试步骤 | 1. 发送 t 2. 检查是否直接发送到 tmux |
| 预期结果 | 跳过队列，直接发送 |

#### TC-04: 特殊命令发送
| 项目 | 内容 |
|------|------|
| 用例名称 | /LEFT /RIGHT /UP /DOWN 直接发送给 tmux |
| 前置条件 | 用户发送 /LEFT 等命令 |
| 测试步骤 | 1. 发送 /LEFT 2. 检查 tmux 是否收到左箭头 |
| 预期结果 | 命令直接发送到 tmux |

#### TC-05: Thinking 检测
| 项目 | 内容 |
|------|------|
| 用例名称 | 检测 tmux "Thinking" 状态 |
| 前置条件 | tmux 正在执行 Kiro AI |
| 测试步骤 | 1. A队列有消息待发送 2. tmux 显示 "Thinking" |
| 预期结果 | 检测到 Thinking，更新 ACK 询问 |

#### TC-06: t/n/y 决策处理
| 项目 | 内容 |
|------|------|
| 用例名称 | t/n/y 决策处理 |
| 前置条件 | ACK 显示 "思考中, t/n/y?" |
| 测试步骤 | 1. 发送 t 2. 检查是否直接发送 |
| 预期结果 | t 跳过队列直接发送 |

#### TC-07: 清空队列
| 项目 | 内容 |
|------|------|
| 用例名称 | n 决策清空未发送队列 |
| 前置条件 | A队列有多个待发送消息 |
| 测试步骤 | 1. 发送 n 2. 检查队列是否清空 |
| 预期结果 | 未发送队列清空，ACK 删除 |

#### TC-08: tmux 发送规则
| 项目 | 内容 |
|------|------|
| 用例名称 | 发送 tmux 前 sleep 1s 再发 ENTER |
| 前置条件 | A队列有消息待发送 |
| 测试步骤 | 1. 触发发送 2. 检查日志时间间隔 |
| 预期结果 | 发送消息后等待 1 秒再发送 ENTER |

#### TC-09: A队列创建
| 项目 | 内容 |
|------|------|
| 用例名称 | 语音识别前创建 A队列 |
| 前置条件 | 用户发送语音消息 |
| 测试步骤 | 1. 发送语音 2. 检查 queue/ 目录 |
| 预期结果 | A队列文件存在，status=pending → ready |

#### TC-10: A队列顺序处理
| 项目 | 内容 |
|------|------|
| 用例名称 | A队列按时间顺序发送到 tmux |
| 前置条件 | 创建多个 A队列文件 |
| 测试步骤 | 1. 创建 A1, A2, A3 (不同时间戳) 2. 运行 kiro_handler |
| 预期结果 | 按 A1 → A2 → A3 顺序发送到 tmux |

#### TC-11: B队列顺序处理
| 项目 | 内容 |
|------|------|
| 用例名称 | B队列按时间顺序发送给用户 |
| 前置条件 | 创建多个 B队列文件 |
| 测试步骤 | 1. 创建 B1, B2, B3 (不同时间戳) 2. 运行 kiro_handler |
| 预期结果 | 按 B1 → B2 → B3 顺序发送给用户 |

#### TC-12: ACK 消息删除
| 项目 | 内容 |
|------|------|
| 用例名称 | 收到 Kiro 回复后删除 ACK 消息 |
| 前置条件 | B队列 status=ready，ack_message_id 存在 |
| 测试步骤 | 1. 模拟 B队列处理 2. 检查 ACK 消息是否删除 |
| 预期结果 | ACK 消息被正确删除 |

#### TC-13: 错误处理
| 项目 | 内容 |
|------|------|
| 用例名称 | 网络/TOKEN 错误时添加删除按钮 |
| 前置条件 | 模拟网络/TOKEN 错误 |
| 测试步骤 | 1. 触发错误 2. 检查 ACK 消息是否添加删除按钮 |
| 预期结果 | 删除按钮正确添加，用户可手动删除 |

#### TC-14: 队列清理
| 项目 | 内容 |
|------|------|
| 用例名称 | 已处理文件自动清理 |
| 前置条件 | B队列 status=sent_to_user |
| 测试步骤 | 1. 模拟 B队列完成 2. 检查文件是否删除 |
| 预期结果 | 已处理文件自动删除 |

#### TC-15: /capture 命令
| 项目 | 内容 |
|------|------|
| 用例名称 | /capture 命令捕获 tmux pane |
| 前置条件 | tmux 有内容 |
| 测试步骤 | 1. 发送 /capture 2. 检查是否收到代码块 |
| 预期结果 | tmux 内容以代码块形式发送给用户 |

#### TC-16: /capture 行数限制
| 项目 | 内容 |
|------|------|
| 用例名称 | /capture 超过行数限制时截取 |
| 前置条件 | tmux 有超过 50 行内容 |
| 测试步骤 | 1. 发送 /capture 2. 检查消息行数 |
| 预期结果 | 只发送最新 50 行 |

#### TC-17: /tree 命令
| 项目 | 内容 |
|------|------|
| 用例名称 | /tree 命令树状显示 tmux 结构 |
| 前置条件 | tmux 有多个 session/window/pane |
| 测试步骤 | 1. 发送 /tree 2. 检查返回的树状结构 |
| 预期结果 | 树状结构显示正确，最后一级可复制 |

#### TC-18: /resize-pane 命令
| 项目 | 内容 |
|------|------|
| 用例名称 | /resize-pane 设置窗格高度 |
| 前置条件 | - |
| 测试步骤 | 1. 发送 /resize-pane 100 2. 检查窗格高度 |
| 预期结果 | 窗格高度设置为 100 行 |

#### TC-19: /win_id 命令
| 项目 | 内容 |
|------|------|
| 用例名称 | /win_id 返回当前 win_id |
| 前置条件 | - |
| 测试步骤 | 1. 发送 /win_id 2. 检查返回内容 |
| 预期结果 | 返回当前配置的 win_id |

#### TC-20: /win_id_set 命令
| 项目 | 内容 |
|------|------|
| 用例名称 | /win_id_set 设置并保存 win_id |
| 前置条件 | - |
| 测试步骤 | 1. 发送 /win_id_set 6:master.0 2. 检查配置文件 |
| 预期结果 | win_id 保存到配置文件 |

#### TC-21: /pane_height 命令
| 项目 | 内容 |
|------|------|
| 用例名称 | /pane_height 返回当前窗格高度 |
| 前置条件 | - |
| 测试步骤 | 1. 发送 /pane_height 2. 检查返回内容 |
| 预期结果 | 返回当前窗格高度行数 |

#### TC-22: /cut_max_rows 命令
| 项目 | 内容 |
|------|------|
| 用例名称 | /cut_max_rows 返回最大截取行数 |
| 前置条件 | - |
| 测试步骤 | 1. 发送 /cut_max_rows 2. 检查返回内容 |
| 预期结果 | 返回当前配置的截取行数 |

#### TC-23: /cut_rows_set 命令
| 项目 | 内容 |
|------|------|
| 用例名称 | /cut_rows_set 设置并保存行数 |
| 前置条件 | - |
| 测试步骤 | 1. 发送 /cut_rows_set 100 2. 检查配置文件 |
| 预期结果 | 行数保存到配置文件 |

#### TC-24: /new_win 命令
| 项目 | 内容 |
|------|------|
| 用例名称 | /new_win 创建新窗口 |
| 前置条件 | - |
| 测试步骤 | 1. 发送 /new_win bot api kiro-cli 2. 检查窗口是否创建 |
| 预期结果 | 新窗口创建成功，执行 kiro-cli，切换 win_id |

#### TC-25: /del_win 命令
| 项目 | 内容 |
|------|------|
| 用例名称 | /del_win 删除窗口 |
| 前置条件 | 有可删除的窗口 |
| 测试步骤 | 1. 发送 /del_win 6:master.0 2. 检查窗口是否删除 |
| 预期结果 | 窗口删除成功，使用兄弟窗口 win_id |

### 3.3 测试覆盖率要求

| 模块 | 最低覆盖率 |
|------|------------|
| bot.py (队列相关) | 80% |
| kiro_handler.py | 90% |
| 整体 | 70% |

---

## 四、验收标准

### 4.1 功能验收 (DoD)

| 编号 | 标准 | 验收方法 |
|------|------|----------|
| AC-01 | 用户发送语音后发送 ACK 消息 🎧识别中 | Telegram 检查 ACK 消息 |
| AC-02 | 文本消息跳过 STT，直接显示 ⚙️处理中 | Telegram 检查 ACK 消息 |
| AC-03 | 识别完成后编辑 ACK 消息为 ⚙️处理中 | Telegram 检查 ACK 消息内容 |
| AC-04 | t/n/y 消息跳过队列直接发送 | Telegram 实测 |
| AC-05 | /LEFT /RIGHT /UP /DOWN 直接发送给 tmux | Telegram 实测 |
| AC-06 | 用户发送消息后立即创建 A 队列文件 | 检查 `queue/` 目录文件存在 |
| AC-07 | A队列按时间顺序发送到 tmux | 3条消息顺序发送验证 |
| AC-08 | 检测 tmux "Thinking" 状态 | 日志检查 + 实测 |
| AC-09 | Thinking 时更新 ACK 询问 t/n/y | Telegram 检查 ACK 消息 |
| AC-10 | t/n/y 决策正确处理 | Telegram 实测 |
| AC-11 | n 决策清空未发送队列 | Telegram 实测 |
| AC-12 | tmux 发送前 sleep 1s 再发 ENTER | 日志时间戳验证 |
| AC-13 | B队列按时间顺序发送给用户 | 3条回复顺序发送验证 |
| AC-14 | 收到 Kiro 回复后删除 ACK 消息 | Telegram 检查消息删除 |
| AC-15 | 网络/TOKEN 错误时添加删除按钮 | Telegram 检查按钮显示 |
| AC-16 | /capture 命令正确捕获 tmux 内容 | Telegram 实测 |
| AC-17 | /capture 超过行数限制时截取 | Telegram 实测 |
| AC-18 | /tree 命令树状显示 tmux 结构 | Telegram 实测 |
| AC-19 | /resize-pane 设置窗格高度 | Telegram 实测 |
| AC-20 | /win_id 返回当前 win_id | Telegram 实测 |
| AC-21 | /win_id_set 设置并保存 win_id | 检查配置文件 |
| AC-22 | /pane_height 返回当前窗格高度 | Telegram 实测 |
| AC-23 | /cut_max_rows 返回最大截取行数 | Telegram 实测 |
| AC-24 | /cut_rows_set 设置并保存行数 | 检查配置文件 |
| AC-25 | /new_win 创建新窗口 | Telegram 实测 |
| AC-26 | /del_win 删除窗口 | Telegram 实测 |
| AC-18 | A/B 队列独立，不互相干扰 | 混合消息测试 |
| AC-19 | 处理完成后自动清理队列文件 | 检查文件删除 |

### 4.2 质量验收

| 编号 | 标准 | 验收方法 |
|------|------|----------|
| QC-01 | 单元测试通过率 100% | `pytest tests/ -v` |
| QC-02 | 集成测试通过 | `pytest tests/test_integration.py -v` |
| QC-03 | 代码风格检查通过 | `flake8 tts_bot/ scripts/` |
| QC-04 | 无重复函数定义 | 代码审查 |

### 4.3 性能验收

| 编号 | 标准 | 验收方法 |
|------|------|----------|
| PC-01 | 队列扫描间隔 ≤ 2秒 | 日志时间戳验证 |
| PC-02 | 单条消息处理时间 ≤ 10秒（不含 Kiro 响应） | 日志时间戳验证 |
| PC-03 | 队列文件大小可控（单文件 ≤ 10KB） | 文件大小检查 |

### 4.4 可靠性验收

| 编号 | 标准 | 验收方法 |
|------|------|----------|
| RC-01 | 重启后队列不丢失 | 重启测试 |
| RC-02 | 错误消息可识别（status=error） | 检查错误队列 |
| RC-03 | 队列目录不存在时不崩溃 | 异常测试 |

### 4.5 端到端验收测试

```bash
# 测试步骤
1. 清空 queue/ 目录
2. 发送语音消息 A1
3. 观察 ACK 消息 🎧识别中 → ⚙️处理中
4. 发送语音消息 A2
5. 发送语音消息 A3
6. 发送 t 验证直接发送
7. 发送 /LEFT 验证特殊命令
8. 发送 /tree 验证树状显示
9. 发送 /resize-pane 50 验证调整高度
10. 发送 /capture 验证捕获功能
11. 发送 /win_id 验证获取 win_id
12. 发送 /win_id_set 6:master.0 验证设置 win_id
13. 发送 /cut_rows_set 100 验证设置截取行数
14. 观察 kiro_handler 日志，确认 A1→A2→A3 顺序发送到 tmux
15. 模拟 Kiro 回复 B1, B2, B3
16. 观察用户收到的回复，确认 B1→B2→B3 顺序
17. 观察 ACK 消息是否正确删除
18. 检查 queue/ 目录，所有文件已清理
```

**验收通过标准**：
- [ ] ACK 消息正确创建和编辑
- [ ] 文本消息跳过 STT
- [ ] t/n/y 直接发送
- [ ] /LEFT /RIGHT /UP /DOWN 直接发送给 tmux
- [ ] /tree 命令树状显示 tmux 结构
- [ ] /resize-pane 正确设置窗格高度
- [ ] /win_id 返回当前 win_id
- [ ] /win_id_set 保存配置
- [ ] /pane_height 返回当前高度
- [ ] /cut_max_rows 返回截取行数
- [ ] /cut_rows_set 保存截取行数配置
- [ ] /new_win 创建新窗口
- [ ] /del_win 删除窗口
- [ ] /capture 命令正确捕获 tmux 内容
- [ ] /capture 超过行数限制时正确截取
- [ ] A队列顺序正确
- [ ] B队列顺序正确
- [ ] Thinking 检测正确
- [ ] t/n/y 决策正确
- [ ] n 决策清空未发送队列
- [ ] tmux 发送规则正确
- [ ] ACK 消息正确删除
- [ ] 错误时删除按钮正确显示
- [ ] 无消息丢失
- [ ] 无消息错位
- [ ] 队列文件自动清理
- [ ] 所有测试通过

---

## 五、待确认事项

### Q1: B队列生成方式

Kiro 回复后如何创建 B 队列文件？

- **方案A**: bot_api.py 监听 `/reply` 接口，由外部系统调用此接口创建 B 队列
- **方案B**: kiro_handler 轮询 tmux 窗口内容，检测 Kiro 回复并自动创建 B 队列
- **方案C**: 其他方式

### Q2: t/n/y 配置

t/n/y 决策字符是否需要支持自定义配置？

- **是**: 在配置文件中设置 `TNY_DECISION_CHARS = ['t', 'n', 'y']`
- **否**: 固定使用 t/n/y

### Q3: Thinking 超时

检测到 "Thinking" 后，是否有超时限制？

- **有**: 设置超时时间（如 60 秒）
- **无**: 无限等待用户决策

---

## 六、TODO 列表

### Phase 1: 基础架构

| ID | 任务 | 文件 | 依赖 | 优先级 |
|----|------|------|------|--------|
| T-01 | 添加 t/n/y 配置 | config.py | - | P0 |
| T-02 | 添加 tmux 抽象接口 | tmux_backend.py | - | P0 |
| T-03 | 添加 AI Backend 抽象接口 | ai_backend.py | - | P0 |
| T-04 | 添加 STT Backend 抽象接口 | stt_backend.py | - | P0 |
| T-05 | 添加 Config 配置类 | config.py | T-01 | P0 |
| T-06 | 实现 KiroTmuxBackend | tmux_backend.py | T-02 | P0 |
| T-07 | 实现 KiroAIBackend | ai_backend.py | T-03 | P0 |
| T-08 | 实现 DefaultSTT | stt_backend.py | T-04 | P0 |
| T-09 | 修改 bot.py - ACK 机制 | bot.py | - | P0 |
| T-10 | 修改 bot.py - t/n/y 处理 | bot.py | T-01 | P0 |
| T-11 | 修改 bot.py - 特殊命令 | bot.py | - | P0 |
| T-12 | 修改 kiro_handler.py | kiro_handler.py | T-06 | P0 |

### Phase 2: 完整流程

| ID | 任务 | 文件 | 依赖 | 优先级 |
|----|------|------|------|--------|
| T-13 | Thinking 检测逻辑 | kiro_handler.py | T-07, T-12 | P0 |
| T-14 | t/n/y 决策处理 | kiro_handler.py | T-10, T-12 | P0 |
| T-15 | n 清空队列逻辑 | kiro_handler.py | T-14 | P0 |
| T-16 | tmux sleep 1s + ENTER | kiro_handler.py | - | P0 |
| T-17 | 特殊命令发送逻辑 | kiro_handler.py | T-11 | P0 |
| T-18 | /capture 命令实现 | kiro_handler.py | T-06 | P0 |
| T-19 | B队列处理逻辑 | kiro_handler.py | T-12 | P0 |
| T-20 | ACK 删除逻辑 | kiro_handler.py | T-19 | P0 |
| T-21 | 队列清理逻辑 | kiro_handler.py | T-19 | P1 |
| T-22 | /tree 命令实现 | kiro_handler.py | T-06 | P0 |
| T-23 | /resize-pane 命令实现 | kiro_handler.py | T-06 | P0 |
| T-24 | /win_id 命令实现 | kiro_handler.py | T-06 | P0 |
| T-25 | /win_id_set 命令实现 | kiro_handler.py | T-06 | P0 |
| T-26 | /pane_height 命令实现 | kiro_handler.py | T-06 | P0 |
| T-27 | /cut_max_rows 命令实现 | kiro_handler.py | T-06 | P0 |
| T-28 | /cut_rows_set 命令实现 | kiro_handler.py | T-06 | P0 |
| T-29 | /new_win 命令实现 | kiro_handler.py | T-06 | P0 |
| T-30 | /del_win 命令实现 | kiro_handler.py | T-06 | P0 |
| T-31 | 本地配置存储实现 | kiro_handler.py | - | P0 |

### Phase 3: 测试与验收

| ID | 任务 | 文件 | 依赖 | 优先级 |
|----|------|------|------|--------|
| T-32 | 添加单元测试 | tests/test_queue.py | T-01~T-08 | P1 |
| T-33 | 添加集成测试 | tests/test_integration.py | T-09~T-31 | P1 |
| T-34 | 运行单元测试 | tests/ | T-32 | P0 |
| T-35 | 运行集成测试 | tests/ | T-33 | P0 |
| T-36 | 代码风格检查 | flake8 | 全部代码 | P0 |
| T-37 | 类型检查 | mypy | 全部代码 | P0 |
| T-38 | 手动 E2E 测试 | Telegram 实测 | T-13~T-31 | P0 |

### Phase 4: 待实现（后续迭代）

| ID | 任务 | 说明 |
|----|------|------|
| T-F1 | 实现 OpenCodeAIBackend | OpenCode AI 后端支持 |
| T-F2 | 实现 OpenAIWhisperSTT | OpenAI Whisper STT 支持 |
| T-F3 | 实现 BaiduSTT | 百度语音识别支持 |
| T-F4 | /capture 行数配置 | CAPTURE_MAX_ROWS 运行时配置 |
| T-F5 | Web 配置界面 | 可视化配置管理 |
| T-F6 | 消息历史记录 | 保存对话历史 |
| T-F7 | 多用户支持 | 扩展为多用户架构 |
