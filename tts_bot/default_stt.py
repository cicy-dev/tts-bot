#!/usr/bin/env python3
"""
默认 STT 后端实现
通过 bot_api.py 调用语音识别 API
"""

import os
from typing import Optional

import aiohttp

from .stt_backend import STTBackend


class DefaultSTTBackend(STTBackend):
    """默认 STT 实现"""

    API_URL = "http://localhost:15001/voice_to_text"

    def __init__(self, api_url: Optional[str] = None):
        if api_url:
            self.API_URL = api_url

    async def recognize(self, audio_path: str) -> str:
        """通过 API 识别语音"""
        if not os.path.exists(audio_path):
            return ""

        try:
            async with aiohttp.ClientSession() as session:
                with open(audio_path, "rb") as f:
                    data = aiohttp.FormData()
                    data.add_field("file", f, filename="voice.ogg")
                    async with session.post(self.API_URL, data=data) as resp:
                        result = await resp.json()
                        return result.get("text", "")
        except Exception as e:
            print(f"STT 识别失败: {e}")
            return ""
