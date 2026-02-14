#!/usr/bin/env python3
"""
Redis Session Map - tmux session → bot 映射
全局注册表，handler 读取，bot 注册
"""

import json
import os
import logging
import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
MAP_KEY = "tts:session_map"


class SessionMap:
    """tmux session → bot API 映射"""

    def __init__(self, url: str = None):
        self.client = redis.from_url(url or REDIS_URL, decode_responses=True)

    def register(self, win_id: str, bot_name: str, api_url: str, chat_id: int = 0, bot_token: str = ""):
        """bot 启动时注册: 哪个 tmux 窗口 → 哪个 bot API"""
        self.client.hset(MAP_KEY, win_id, json.dumps({
            "bot_name": bot_name,
            "api_url": api_url,
            "chat_id": chat_id,
            "bot_token": bot_token,
        }, ensure_ascii=False))
        logger.info(f"注册: {win_id} → {bot_name} ({api_url})")

    def unregister(self, win_id: str):
        """bot 停止时注销"""
        self.client.hdel(MAP_KEY, win_id)
        logger.info(f"注销: {win_id}")

    def get(self, win_id: str) -> dict | None:
        """获取某个 tmux 窗口对应的 bot 信息"""
        raw = self.client.hget(MAP_KEY, win_id)
        return json.loads(raw) if raw else None

    def get_all(self) -> dict:
        """获取所有映射 {win_id: {bot_name, api_url, chat_id}}"""
        result = {}
        for win_id, raw in self.client.hgetall(MAP_KEY).items():
            result[win_id] = json.loads(raw)
        return result

    def update_chat_id(self, win_id: str, chat_id: int):
        """更新活跃 chat_id"""
        info = self.get(win_id)
        if info:
            info["chat_id"] = chat_id
            self.client.hset(MAP_KEY, win_id, json.dumps(info, ensure_ascii=False))

    def clear(self):
        """清空所有映射"""
        self.client.delete(MAP_KEY)


# 全局实例
session_map = SessionMap()
