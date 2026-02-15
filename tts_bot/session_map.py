#!/usr/bin/env python3
"""
Bot Config - 使用 bot_config 表替代 session_map
"""

import json
import os
import pymysql
import logging
import threading

logger = logging.getLogger(__name__)

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "tts_bot")


def format_win_id(tmux_session: str, tmux_window: str, pane: int = 0) -> str:
    """生成 tmux win_id: {session}:{window}.{pane}"""
    return f"{tmux_session}:{tmux_window}.{pane}"


class SessionMap:
    """兼容旧接口，实际使用 bot_config 表"""
    def __init__(self):
        self._local = threading.local()

    @property
    def _conn(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = pymysql.connect(
                host=MYSQL_HOST,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DATABASE,
                charset='utf8mb4',
                autocommit=True
            )
        return self._local.conn

    def register(self, win_id: str, bot_name: str, api_url: str, chat_id: int = 0, bot_token: str = "", group: str = "worker"):
        """注册 bot 到 bot_config"""
        c = self._conn.cursor()
        # 解析 win_id: session:window.pane
        parts = win_id.split(":")
        tmux_session = parts[0] if len(parts) > 0 else group
        window_pane = parts[1] if len(parts) > 1 else f"{bot_name}.0"
        tmux_window = window_pane.split(".")[0] if "." in window_pane else window_pane

        c.execute("""
            INSERT INTO bot_config (bot_name, bot_token, chat_id, tmux_session, tmux_window, group_name, api_url, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'active')
            ON DUPLICATE KEY UPDATE
                bot_token=%s, chat_id=%s, tmux_session=%s, tmux_window=%s, group_name=%s, api_url=%s
        """, (bot_name, bot_token, chat_id, tmux_session, tmux_window, group, api_url,
              bot_token, chat_id, tmux_session, tmux_window, group, api_url))
        c.close()
        logger.info(f"注册: {win_id} → {bot_name} (group={group})")

    def get(self, win_id: str) -> dict | None:
        """通过 win_id 获取 bot 信息（win_id 由 tmux_session + tmux_window 动态生成）"""
        # 解析 win_id → tmux_session, tmux_window
        parts = win_id.split(":")
        if len(parts) < 2:
            return None
        tmux_session = parts[0]
        tmux_window = parts[1].split(".")[0] if "." in parts[1] else parts[1]

        c = self._conn.cursor()
        c.execute("""
            SELECT bot_name, api_url, chat_id, bot_token, group_name 
            FROM bot_config 
            WHERE tmux_session=%s AND tmux_window=%s
        """, (tmux_session, tmux_window))
        row = c.fetchone()
        c.close()
        if row:
            return {
                "bot_name": row[0],
                "api_url": row[1],
                "chat_id": row[2],
                "bot_token": row[3],
                "group": row[4]
            }
        return None

    def get_all(self) -> dict:
        """获取所有 bot，key 为动态生成的 win_id"""
        c = self._conn.cursor()
        c.execute("""
            SELECT tmux_session, tmux_window, bot_name, api_url, chat_id, bot_token, group_name
            FROM bot_config
            WHERE status='active'
        """)
        rows = c.fetchall()
        c.close()
        result = {}
        for row in rows:
            win_id = format_win_id(row[0], row[1])
            result[win_id] = {
                "bot_name": row[2],
                "api_url": row[3],
                "chat_id": row[4],
                "bot_token": row[5],
                "group": row[6]
            }
        return result

    def update_chat_id(self, win_id: str, chat_id: int):
        """更新 chat_id"""
        parts = win_id.split(":")
        if len(parts) < 2:
            return
        tmux_session = parts[0]
        tmux_window = parts[1].split(".")[0] if "." in parts[1] else parts[1]
        c = self._conn.cursor()
        c.execute("UPDATE bot_config SET chat_id=%s WHERE tmux_session=%s AND tmux_window=%s", (chat_id, tmux_session, tmux_window))
        c.close()

    def set_var(self, key: str, value):
        """设置全局变量"""
        c = self._conn.cursor()
        c.execute("""
            INSERT INTO global_vars (key_name, value)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE value=%s
        """, (key, json.dumps(value), json.dumps(value)))
        c.close()

    def get_var(self, key: str, default=None):
        """获取全局变量"""
        c = self._conn.cursor()
        c.execute("SELECT value FROM global_vars WHERE key_name=%s", (key,))
        row = c.fetchone()
        c.close()
        if row:
            try:
                return json.loads(row[0])
            except:
                return row[0]
        return default


# 全局实例
session_map = SessionMap()
