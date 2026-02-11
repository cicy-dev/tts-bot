#!/usr/bin/env python3
"""
AI 后端抽象接口
支持可扩展的 AI 服务
"""

from abc import ABC, abstractmethod


class AIBackend(ABC):
    """AI 后端抽象接口"""

    @abstractmethod
    def check_thinking(self) -> bool:
        """检测 AI 是否处于 Thinking 状态

        Returns:
            是否处于 Thinking 状态
        """
        pass

    @abstractmethod
    def extract_reply(self) -> str:
        """提取 AI 回复（分隔 Thinking 和正式回答）

        Returns:
            AI 回复内容
        """
        pass

    @abstractmethod
    def send_message(self, text: str) -> bool:
        """发送消息到 AI

        Args:
            text: 消息内容

        Returns:
            是否发送成功
        """
        pass
