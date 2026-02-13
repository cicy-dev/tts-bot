#!/usr/bin/env python3
"""
Kiro Tmux 后端实现
"""

import os
import subprocess
from typing import Optional

from .tmux_backend import TmuxBackend
from .config import config


TMUX_SOCKET = os.environ.get("TMUX_SOCKET", "")
TMUX_PREFIX = f"tmux -S {TMUX_SOCKET}" if TMUX_SOCKET else "tmux"


def run_cmd(cmd: str) -> tuple[str, int]:
    """执行 shell 命令"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout, result.returncode
    except Exception as e:
        return str(e), 1


class KiroTmuxBackend(TmuxBackend):
    """Kiro tmux 后端实现"""

    def send_text(self, text: str, win_id: str) -> bool:
        """发送文本到 tmux"""
        escaped = text.replace("'", "'\\''")
        cmd = f"{TMUX_PREFIX} send-keys -t '{win_id}' '{escaped}'"
        output, code = run_cmd(cmd)
        return code == 0

    def send_keys(self, keys: str, win_id: str) -> bool:
        """发送特殊按键到 tmux"""
        key_map = {
            "ENTER": "Enter",
            "LEFT": "Left",
            "RIGHT": "Right",
            "UP": "Up",
            "DOWN": "Down",
            "CTRL+C": "C-c",
            "CMD+C": "C-c",
        }
        key = key_map.get(keys, keys)
        cmd = f"{TMUX_PREFIX} send-keys -t '{win_id}' '{key}'"
        output, code = run_cmd(cmd)
        return code == 0

    def capture_pane(self, win_id: str, max_rows: Optional[int] = None) -> str:
        """捕获 tmux pane 内容"""
        if max_rows is None:
            max_rows = config.capture_max_rows

        cmd = f"{TMUX_PREFIX} capture-pane -t '{win_id}' -p"
        output, code = run_cmd(cmd)

        if code != 0:
            return f"捕获失败: {output}"

        lines = output.rstrip().split("\n")

        if max_rows and len(lines) > max_rows:
            lines = lines[-max_rows:]

        return "\n".join(lines)

    def check_thinking(self, win_id: str) -> bool:
        """检测 AI 是否处于 Thinking 状态"""
        output, code = run_cmd(f"{TMUX_PREFIX} capture-pane -t '{win_id}' -p -S -10")
        if code != 0:
            return False
        lines = output.rstrip().split("\n")
        return any("Thinking" in line for line in lines)

    def get_pane_height(self, win_id: str) -> int:
        """获取当前窗格高度"""
        output, code = run_cmd(f"{TMUX_PREFIX} display -t '{win_id}' -p '#{{pane_height}}'")
        if code == 0:
            try:
                return int(output.strip())
            except ValueError:
                pass
        return 0

    def resize_pane(self, win_id: str, height: int) -> bool:
        """设置窗格高度"""
        cmd = f"{TMUX_PREFIX} resize-pane -t '{win_id}' -y {height}"
        output, code = run_cmd(cmd)
        return code == 0

    def tree_sessions(self) -> str:
        """树状显示所有 session、window、pane"""
        output, code = run_cmd(f"{TMUX_PREFIX} list-sessions -F '#{{session_name}}' 2>/dev/null")
        if code != 0:
            return "没有运行中的 session"

        sessions = [s for s in output.strip().split("\n") if s]
        lines = []

        for i, session in enumerate(sessions):
            is_last_session = i == len(sessions) - 1
            prefix = "└──" if is_last_session else "├──"
            lines.append(f"{prefix} {session}")

            # 列出 windows
            win_output, _ = run_cmd(
                f"{TMUX_PREFIX} list-windows -t '{session}' -F '#{{window_index}} #{{window_name}}'"
            )
            windows = [w for w in win_output.strip().split("\n") if w]

            for j, window in enumerate(windows):
                parts = window.split(None, 1)
                if len(parts) < 2:
                    continue
                win_idx = parts[0]
                win_name = parts[1]
                is_last_win = j == len(windows) - 1
                win_prefix = "└──" if is_last_win else "├──"
                indent = "    " if is_last_session else "│   "
                lines.append(f"{indent}{win_prefix} {win_idx} {win_name}")

                # 列出 panes
                pane_output, _ = run_cmd(
                    f"{TMUX_PREFIX} list-panes -t '{session}:{win_idx}' -F '#{{pane_index}} #{{pane_current_command}}'"
                )
                panes = [p for p in pane_output.strip().split("\n") if p]

                for k, pane in enumerate(panes):
                    parts = pane.split(None, 1)
                    if len(parts) < 2:
                        continue
                    pane_idx = parts[0]
                    pane_cmd = parts[1]
                    is_last_pane = k == len(panes) - 1
                    pane_prefix = "└──" if is_last_pane else "├──"
                    pane_indent = "    " if is_last_win else "│   "
                    pane_id = f"{session}:{win_idx}.{pane_idx}"
                    lines.append(
                        f"{indent}{pane_indent}{pane_prefix} {pane_id} {pane_cmd}"
                    )

        return "\n".join(lines)

    def new_window(self, session: str, window: str, command: str, win_id: str) -> bool:
        """创建新窗口"""
        # 创建新窗口
        cmd1 = f"{TMUX_PREFIX} new-window -t '{session}' -n '{window}'"
        _, code1 = run_cmd(cmd1)
        if code1 != 0:
            return False

        # 发送初始命令
        cmd2 = f"{TMUX_PREFIX} send-keys -t '{session}:{window}' '{command}'"
        _, code2 = run_cmd(cmd2)
        if code2 != 0:
            return False

        # 发送回车
        cmd3 = f"{TMUX_PREFIX} send-keys -t '{session}:{window}' 'Enter'"
        _, code3 = run_cmd(cmd3)

        return code3 == 0

    def del_window(self, win_id: str) -> bool:
        """删除窗口"""
        cmd = f"{TMUX_PREFIX} kill-window -t '{win_id}'"
        output, code = run_cmd(cmd)
        return code == 0
