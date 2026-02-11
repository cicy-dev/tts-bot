#!/usr/bin/env python3
"""
STT 后端抽象接口
支持可扩展的语音识别服务
"""

from abc import ABC, abstractmethod
from typing import Awaitable


class STTBackend(ABC):
    """语音识别后端抽象接口"""

    @abstractmethod
    async def recognize(self, audio_path: str) -> str:
        """将音频文件识别为文字

        Args:
            audio_path: 音频文件路径

        Returns:
            识别出的文字
        """
        pass
