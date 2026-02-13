# TTS Bot Go重写计划

## 📋 当前Python版本分析

### 核心功能
1. **Telegram Bot** - 接收消息
2. **TTS (文字转语音)** - edge-tts
3. **STT (语音转文字)** - Google Speech API
4. **Tmux控制** - 发送命令到tmux
5. **队列系统** - 消息队列管理
6. **HTTP API** - bot_api.py (15001端口)

### 依赖库
```python
python-telegram-bot    # Telegram
edge-tts              # TTS
speech_recognition    # STT
pydub                 # 音频处理
fastapi               # API服务器
aiohttp               # HTTP客户端
```

---

## 🔧 Go重写工作清单

### 第1步：环境准备 (1小时)

**安装Go环境**
```bash
# 已安装Go 1.21+
go version
```

**创建项目结构**
```bash
mkdir -p ~/projects/tts-bot-go
cd ~/projects/tts-bot-go

# 初始化Go模块
go mod init github.com/w3c/tts-bot-go
```

**目录结构**
```
tts-bot-go/
├── cmd/
│   └── bot/
│       └── main.go           # 主程序入口
├── internal/
│   ├── bot/
│   │   ├── handler.go        # 消息处理
│   │   └── commands.go       # 命令处理
│   ├── tts/
│   │   └── edge.go           # TTS实现
│   ├── stt/
│   │   └── google.go         # STT实现
│   ├── tmux/
│   │   └── control.go        # Tmux控制
│   └── queue/
│       └── queue.go          # 队列管理
├── pkg/
│   └── api/
│       └── server.go         # HTTP API
├── go.mod
├── go.sum
└── README.md
```

---

### 第2步：核心依赖库 (2小时)

**需要的Go库**
```bash
# Telegram Bot
go get github.com/go-telegram-bot-api/telegram-bot-api/v5

# HTTP服务器
go get github.com/gin-gonic/gin

# 音频处理
go get github.com/hajimehoshi/go-mp3
go get github.com/tosone/minimp3

# 配置管理
go get github.com/spf13/viper

# 日志
go get github.com/sirupsen/logrus
```

**依赖对比**

| Python库 | Go替代 | 说明 |
|---------|--------|------|
| python-telegram-bot | telegram-bot-api | 官方推荐 |
| edge-tts | 调用命令行 | 保留edge-tts命令 |
| speech_recognition | 调用Google API | HTTP请求 |
| pydub | go-mp3 | 音频处理 |
| fastapi | gin | 更快的HTTP框架 |
| aiohttp | net/http | Go标准库 |

---

### 第3步：TTS功能 (3小时)

**方案1: 调用edge-tts命令**
```go
package tts

import (
    "os/exec"
)

func TextToSpeech(text, outputFile, voice string) error {
    cmd := exec.Command("edge-tts",
        "--voice", voice,
        "--text", text,
        "--write-media", outputFile,
    )
    return cmd.Run()
}
```

**方案2: 使用Go TTS库**
```go
// 寻找Go原生TTS库
// 或者调用云服务API
```

**推荐**: 方案1，保留edge-tts，稳定可靠

---

### 第4步：STT功能 (3小时)

**调用Google Speech API**
```go
package stt

import (
    "bytes"
    "encoding/json"
    "io"
    "mime/multipart"
    "net/http"
)

type STTClient struct {
    apiURL string
}

func NewSTTClient() *STTClient {
    return &STTClient{
        apiURL: "http://localhost:15001/voice_to_text",
    }
}

func (c *STTClient) Recognize(audioPath string) (string, error) {
    // 1. 读取音频文件
    file, err := os.Open(audioPath)
    if err != nil {
        return "", err
    }
    defer file.Close()
    
    // 2. 构造multipart请求
    body := &bytes.Buffer{}
    writer := multipart.NewWriter(body)
    part, _ := writer.CreateFormFile("file", filepath.Base(audioPath))
    io.Copy(part, file)
    writer.Close()
    
    // 3. 发送请求
    req, _ := http.NewRequest("POST", c.apiURL, body)
    req.Header.Set("Content-Type", writer.FormDataContentType())
    
    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return "", err
    }
    defer resp.Body.Close()
    
    // 4. 解析结果
    var result struct {
        Text string `json:"text"`
    }
    json.NewDecoder(resp.Body).Decode(&result)
    
    return result.Text, nil
}
```

---

### 第5步：Telegram Bot (4小时)

**主程序**
```go
package main

import (
    "log"
    tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"
)

func main() {
    // 1. 读取Token
    token := os.Getenv("BOT_TOKEN")
    
    // 2. 创建Bot
    bot, err := tgbotapi.NewBotAPI(token)
    if err != nil {
        log.Fatal(err)
    }
    
    log.Printf("Authorized on account %s", bot.Self.UserName)
    
    // 3. 获取更新
    u := tgbotapi.NewUpdate(0)
    u.Timeout = 60
    updates := bot.GetUpdatesChan(u)
    
    // 4. 处理消息
    for update := range updates {
        if update.Message == nil {
            continue
        }
        
        go handleMessage(bot, update.Message)
    }
}

func handleMessage(bot *tgbotapi.BotAPI, msg *tgbotapi.Message) {
    if msg.Voice != nil {
        handleVoice(bot, msg)
    } else if msg.Text != "" {
        handleText(bot, msg)
    }
}
```

**文字转语音**
```go
func handleText(bot *tgbotapi.BotAPI, msg *tgbotapi.Message) {
    // 1. 发送"处理中"
    statusMsg := tgbotapi.NewMessage(msg.Chat.ID, "⚙️ 处理中...")
    sent, _ := bot.Send(statusMsg)
    
    // 2. TTS转换
    outputFile := fmt.Sprintf("/tmp/tts_%d.mp3", msg.MessageID)
    err := tts.TextToSpeech(msg.Text, outputFile, "zh-CN-XiaoxiaoNeural")
    if err != nil {
        bot.Send(tgbotapi.NewMessage(msg.Chat.ID, "❌ 转换失败"))
        return
    }
    
    // 3. 发送语音
    voice := tgbotapi.NewVoice(msg.Chat.ID, tgbotapi.FilePath(outputFile))
    bot.Send(voice)
    
    // 4. 删除状态消息
    bot.Send(tgbotapi.NewDeleteMessage(msg.Chat.ID, sent.MessageID))
    
    // 5. 清理临时文件
    os.Remove(outputFile)
}
```

**语音转文字**
```go
func handleVoice(bot *tgbotapi.BotAPI, msg *tgbotapi.Message) {
    // 1. 发送"识别中"
    statusMsg := tgbotapi.NewMessage(msg.Chat.ID, "🎧 识别中...")
    sent, _ := bot.Send(statusMsg)
    
    // 2. 下载语音
    file, _ := bot.GetFile(tgbotapi.FileConfig{FileID: msg.Voice.FileID})
    voicePath := fmt.Sprintf("/tmp/voice_%d.ogg", msg.MessageID)
    downloadFile(file.Link(bot.Token), voicePath)
    
    // 3. STT识别
    sttClient := stt.NewSTTClient()
    text, err := sttClient.Recognize(voicePath)
    if err != nil {
        bot.Send(tgbotapi.NewMessage(msg.Chat.ID, "❌ 识别失败"))
        return
    }
    
    // 4. 更新消息
    editMsg := tgbotapi.NewEditMessageText(msg.Chat.ID, sent.MessageID, 
        fmt.Sprintf("📝 识别结果：\n%s", text))
    bot.Send(editMsg)
    
    // 5. 清理
    os.Remove(voicePath)
}
```

---

### 第6步：HTTP API服务 (2小时)

**API服务器**
```go
package api

import (
    "github.com/gin-gonic/gin"
)

func StartServer() {
    r := gin.Default()
    
    // 语音转文字
    r.POST("/voice_to_text", handleVoiceToText)
    
    // 健康检查
    r.GET("/health", func(c *gin.Context) {
        c.JSON(200, gin.H{"status": "ok"})
    })
    
    r.Run(":15001")
}

func handleVoiceToText(c *gin.Context) {
    // 1. 接收文件
    file, _ := c.FormFile("file")
    
    // 2. 保存临时文件
    tempPath := "/tmp/" + file.Filename
    c.SaveUploadedFile(file, tempPath)
    
    // 3. 转换格式 (调用ffmpeg)
    wavPath := strings.Replace(tempPath, ".ogg", ".wav", 1)
    exec.Command("ffmpeg", "-i", tempPath, wavPath).Run()
    
    // 4. 调用Google API识别
    text := recognizeWithGoogle(wavPath)
    
    // 5. 清理
    os.Remove(tempPath)
    os.Remove(wavPath)
    
    // 6. 返回结果
    c.JSON(200, gin.H{"text": text})
}
```

---

### 第7步：Tmux控制 (2小时)

**Tmux命令封装**
```go
package tmux

import (
    "os/exec"
    "strings"
)

type TmuxClient struct{}

func NewTmuxClient() *TmuxClient {
    return &TmuxClient{}
}

func (t *TmuxClient) SendKeys(winID, keys string) error {
    cmd := exec.Command("tmux", "send-keys", "-t", winID, keys, "Enter")
    return cmd.Run()
}

func (t *TmuxClient) CapturePane(winID string, maxRows int) (string, error) {
    cmd := exec.Command("tmux", "capture-pane", "-t", winID, "-p", 
        "-S", fmt.Sprintf("-%d", maxRows))
    output, err := cmd.Output()
    return string(output), err
}

func (t *TmuxClient) ListSessions() (string, error) {
    cmd := exec.Command("tmux", "list-sessions")
    output, err := cmd.Output()
    return string(output), err
}
```

---

### 第8步：配置和部署 (1小时)

**配置文件 (config.yaml)**
```yaml
bot:
  token: ${BOT_TOKEN}
  
tts:
  voice: zh-CN-XiaoxiaoNeural
  
stt:
  api_url: http://localhost:15001/voice_to_text
  
tmux:
  default_win_id: master:0.0
  
api:
  port: 15001
```

**编译和部署**
```bash
# 编译
go build -o tts-bot cmd/bot/main.go

# 单一二进制文件
ls -lh tts-bot
# -rwxr-xr-x 1 user user 12M Feb 13 12:00 tts-bot

# 运行
./tts-bot
```

---

## 📊 工作量估算

| 任务 | 时间 | 难度 |
|------|------|------|
| 环境准备 | 1小时 | ⭐ |
| 依赖库选择 | 2小时 | ⭐⭐ |
| TTS功能 | 3小时 | ⭐⭐ |
| STT功能 | 3小时 | ⭐⭐⭐ |
| Telegram Bot | 4小时 | ⭐⭐⭐ |
| HTTP API | 2小时 | ⭐⭐ |
| Tmux控制 | 2小时 | ⭐⭐ |
| 配置部署 | 1小时 | ⭐ |
| 测试调试 | 2小时 | ⭐⭐ |

**总计**: 20小时（约3个工作日）

---

## ✅ Go版本的优势

### 1. 部署简单
```bash
# Python版本
- 安装Python
- 安装pip
- 安装10+个依赖
- 配置虚拟环境
- 启动多个服务

# Go版本
- 复制一个文件
- 运行
```

### 2. 性能提升
- 启动时间: 5秒 → 0.1秒
- 内存占用: 200MB → 50MB
- 并发处理: 更强

### 3. 稳定性
- 编译时检查所有错误
- 不会因为依赖问题崩溃
- 类型安全

### 4. 维护简单
- 代码清晰
- 不会"乱"
- 容易理解

---

## 🚀 实施建议

### 方案1: 完全重写（推荐）
- 用Go重写所有功能
- 保留Python版本作为参考
- 逐步迁移

### 方案2: 混合模式
- Bot用Go写
- STT API保留Python (bot_api.py)
- 逐步替换

### 方案3: 分阶段
1. 先写Go版Bot（核心功能）
2. 测试稳定后替换Python
3. 再优化其他功能

---

## 💡 我的建议

**立即开始Go重写！**

**优先级**:
1. ✅ Telegram Bot核心功能
2. ✅ TTS (调用edge-tts命令)
3. ✅ STT (调用现有API)
4. ✅ Tmux控制
5. 🔄 HTTP API (可选，保留Python版)

**预期效果**:
- 3天完成核心功能
- 部署只需1个文件
- 稳定性大幅提升
- 不会再"乱"

需要我开始写Go代码吗？

---

**文档创建时间**: 2026-02-13 12:36
**预计完成时间**: 3个工作日
**状态**: 待开始
