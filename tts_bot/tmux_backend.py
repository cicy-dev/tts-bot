#!/usr/bin/env python3
"""
Tmux 后端抽象接口
支持可扩展的 tmux 操作
"""

from abc import ABC, abstractmethod
from typing import Optional


class TmuxBackend(ABC):
    """tmux 后端抽象接口"""

    @abstractmethod
    def send_text(self, text: str, win_id: str) -> bool:
        """发送文本到 tmux

        Args:
            text: 要发送的文本
            win_id: tmux 目标窗口 ID

        Returns:
            是否发送成功
        """
        pass

    @abstractmethod
    def send_keys(self, keys: str, win_id: str) -> bool:
        """发送特殊按键到 tmux

        Args:
            keys: 按键名称 (LEFT, RIGHT, UP, DOWN, ENTER, etc.)
            win_id: tmux 目标窗口 ID

        Returns:
            是否发送成功
        """
        pass

    @abstractmethod
    def capture_pane(self, win_id: str, max_rows: Optional[int] = None) -> str:
        """捕获 tmux pane 内容

        Args:
            win_id: tmux 目标窗口 ID
            max_rows: 最大行数限制，None=使用默认配置

        Returns:
            tmux pane 内容
        """
        pass

    @abstractmethod
    def check_thinking(self, win_id: str) -> bool:
        """检测 AI 是否处于 Thinking 状态

        Args:
            win_id: tmux 目标窗口 ID

        Returns:
            是否处于 Thinking 状态
        """
        pass

    @abstractmethod
    def get_pane_height(self, win_id: str) -> int:
        """获取当前窗格高度

        Args:
            win_id: tmux 目标窗口 ID

        Returns:
            窗格高度行数
        """
        pass

    @abstractmethod
    def resize_pane(self, win_id: str, height: int) -> bool:
        """设置窗格高度

        Args:
            win_id: tmux 目标窗口 ID
            height: 目标高度行数

        Returns:
            是否设置成功
        """
        pass

    @abstractmethod
    def tree_sessions(self) -> str:
        """树状显示所有 session、window、pane

        Returns:
            树状结构字符串
        """
        pass

    @abstractmethod
    def new_window(self, session: str, window: str, command: str, win_id: str) -> bool:
        """创建新窗口

        Args:
            session: session 名称
            window: window 名称
            command: 初始执行命令
            win_id: 当前 win_id（用于更新）

        Returns:
            是否创建成功
        """
        pass

    @abstractmethod
    def del_window(self, win_id: str) -> bool:
        """删除窗口

        Args:
            win_id: 要删除的窗口 ID

        Returns:
            是否删除成功
        """
        pass
