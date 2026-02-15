#!/usr/bin/env python3
"""
TTS Bot 配置管理
支持本地配置文件存储，实现配置持久化
"""

import json
import os
from pathlib import Path
from typing import Optional, List

CONFIG_PATH = os.path.expanduser("~/.tts-bot/config.json")

class Config:
    """TTS Bot 配置类"""

    def __init__(self):
        self.cut_max_rows: Optional[int] = None
        self.init_code: str = "kiro-cli"
        self.tny_decision_chars: List[str] = ["t", "n", "y"]
        self.tmux_send_delay: float = 1.0
        self.work_dir: str = ""
        self._load()

    def _load(self) -> None:
        """从本地配置文件加载"""
        config_file = Path(CONFIG_PATH)
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.cut_max_rows = data.get("cut_max_rows", self.cut_max_rows)
                self.init_code = data.get("init_code", self.init_code)
                self.tny_decision_chars = data.get(
                    "tny_decision_chars", self.tny_decision_chars
                )
                self.tmux_send_delay = data.get("tmux_send_delay", self.tmux_send_delay)
            except Exception as e:
                print(f"⚠️ 配置文件加载失败: {e}，使用默认配置")

    def _save(self) -> None:
        """保存配置到本地文件"""
        config_dir = Path(CONFIG_PATH).parent
        config_dir.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                "cut_max_rows": self.cut_max_rows,
                "init_code": self.init_code,
                "tny_decision_chars": self.tny_decision_chars,
                "tmux_send_delay": self.tmux_send_delay,
            }
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 配置文件保存失败: {e}")

    def set_cut_max_rows(self, rows: Optional[int]) -> None:
        """设置最大截取行数"""
        self.cut_max_rows = rows
        self._save()

    def is_tny_char(self, char: str) -> bool:
        """检查字符是否为 t/n/y 决策字符"""
        return char in self.tny_decision_chars

    @property
    def capture_max_rows(self) -> int:
        """获取捕获最大行数（None 时默认 50）"""
        return self.cut_max_rows if self.cut_max_rows is not None else 50


# 全局配置实例
config = Config()
