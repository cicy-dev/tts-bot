"""消息转发配置"""
import os

# 本地API地址（需要通过公网IP或隧道访问）
LOCAL_API_URL = os.getenv("LOCAL_API_URL", "http://localhost:15001")

# 是否启用转发模式
FORWARD_ENABLED = os.getenv("FORWARD_ENABLED", "false").lower() == "true"
