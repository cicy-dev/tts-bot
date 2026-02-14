#!/usr/bin/env python3
"""
tmux 管理工具
"""
import subprocess
import sys


def run_cmd(cmd):
    """执行命令并返回输出"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        return result.stdout, result.returncode
    except Exception as e:
        return str(e), 1


def tree():
    """树状显示所有 session、window、pane"""
    output, code = run_cmd("tmux list-sessions -F '#{session_name}' 2>/dev/null")
    if code != 0:
        print("没有运行中的 session")
        return

    sessions = [s for s in output.strip().split("\n") if s]
    lines = []

    for i, session in enumerate(sessions):
        is_last_session = i == len(sessions) - 1
        prefix = "└──" if is_last_session else "├──"
        lines.append(f"{prefix} {session}")

        # 列出 windows
        win_output, _ = run_cmd(
            f"tmux list-windows -t '{session}' -F '#{{window_index}} #{{window_name}}'"
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
                f"tmux list-panes -t '{session}:{win_idx}' -F '#{{pane_index}} #{{pane_current_command}}'"
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
                    f"{indent}{pane_indent}{pane_prefix} {pane_id}"
                )

    print("\n".join(lines))


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ["--tree", "-t"]:
        tree()
    else:
        print("Usage: tx.py --tree/-t")
        sys.exit(1)


if __name__ == "__main__":
    main()
