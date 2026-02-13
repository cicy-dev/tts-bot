# Docker 部署指南

## 快速开始

### 美国服务器部署

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 香港服务器部署

```bash
# 构建镜像
docker-compose -f docker-compose.hk.yml build

# 启动服务
docker-compose -f docker-compose.hk.yml up -d

# 查看日志
docker-compose -f docker-compose.hk.yml logs -f

# 停止服务
docker-compose -f docker-compose.hk.yml down
```

## 配置说明

### 环境变量

- `.env.us` - 美国服务器配置
- `.env.hk` - 香港服务器配置

### 数据目录

- `./data-us/` - 美国数据（队列、日志、配置）
- `./data-hk/` - 香港数据

### Token 配置

在 `.env.us` 和 `.env.hk` 中配置不同的 Bot Token。

## 管理命令

```bash
# 重启服务
docker-compose restart

# 查看状态
docker-compose ps

# 进入容器
docker-compose exec tts-bot-us bash

# 查看实时日志
docker-compose logs -f tts-bot-us

# 更新代码后重新部署
docker-compose down
docker-compose build
docker-compose up -d
```

## 故障排查

```bash
# 检查容器状态
docker ps -a

# 查看容器日志
docker logs tts-bot-us

# 检查网络
docker network ls

# 清理并重建
docker-compose down -v
docker-compose up -d --build
```

## 优势

1. ✅ 环境隔离 - 每个Bot独立运行
2. ✅ 依赖管理 - 所有依赖打包在镜像中
3. ✅ 自动重启 - 崩溃后自动恢复
4. ✅ 日志管理 - 自动轮转，限制大小
5. ✅ 一键部署 - 简化运维流程
