#!/usr/bin/env python3
"""Redis 队列 - 替代文件队列"""

import json
import time
import logging
import os
from typing import Optional

import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# 队列 key
Q_PENDING = "tts:queue:pending"
Q_PROCESSING = "tts:queue:processing"
MSG_PREFIX = "tts:msg:"


class RedisQueue:
    """Redis 消息队列"""

    def __init__(self, url: str = None):
        self.client = redis.from_url(url or REDIS_URL, decode_responses=True)

    def push(self, msg_id: str, data: dict) -> None:
        """添加消息到队列"""
        data["status"] = "pending"
        data["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        data["updated_at"] = data["created_at"]
        self.client.set(f"{MSG_PREFIX}{msg_id}", json.dumps(data, ensure_ascii=False))
        self.client.lpush(Q_PENDING, msg_id)
        logger.info(f"队列推入: {msg_id}")

    def pop(self, timeout: int = 5) -> Optional[tuple]:
        """阻塞获取消息，返回 (msg_id, data) 或 None"""
        result = self.client.brpoplpush(Q_PENDING, Q_PROCESSING, timeout)
        if not result:
            return None
        raw = self.client.get(f"{MSG_PREFIX}{result}")
        if not raw:
            return None
        data = json.loads(raw)
        data["status"] = "processing"
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.client.set(f"{MSG_PREFIX}{result}", json.dumps(data, ensure_ascii=False))
        return result, data

    def done(self, msg_id: str) -> None:
        """标记完成"""
        self.client.lrem(Q_PROCESSING, 1, msg_id)
        self._update_status(msg_id, "done")

    def error(self, msg_id: str) -> None:
        """标记失败"""
        self.client.lrem(Q_PROCESSING, 1, msg_id)
        self._update_status(msg_id, "error")

    def update(self, msg_id: str, data: dict) -> None:
        """更新消息数据"""
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.client.set(f"{MSG_PREFIX}{msg_id}", json.dumps(data, ensure_ascii=False))

    def get(self, msg_id: str) -> Optional[dict]:
        """获取消息"""
        raw = self.client.get(f"{MSG_PREFIX}{msg_id}")
        return json.loads(raw) if raw else None

    def _update_status(self, msg_id: str, status: str) -> None:
        data = self.get(msg_id)
        if data:
            data["status"] = status
            self.update(msg_id, data)

    def ping(self) -> bool:
        try:
            return self.client.ping()
        except Exception:
            return False


# 全局实例
rq = RedisQueue()
