#!/usr/bin/env python3
"""
QA Matcher - 从终端快照匹配问答对
读 terminal_snapshot + qa_pair，提取回复，更新 answer

独立进程，不依赖 Redis，不回复 TG
"""

import os
import sys
import time
import logging
import pymysql

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [qa_matcher] %(levelname)s %(message)s"
)
log = logging.getLogger("qa_matcher")

MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
POLL_INTERVAL = 3

SYSTEM_PATTERNS = [
    "λ >", "▸ Credits:", "> What would you like to do next",
    "I will run the following command:", "Purpose:", "(using tool:",
    "- Completed in", "Allow this action?", "[y/n/t]",
    "Tool use was cancelled", "Tool ran without output", "Thinking...",
]


def is_system(line):
    s = line.strip()
    if not s:
        return True
    return any(p in s for p in SYSTEM_PATTERNS)


def db():
    return pymysql.connect(
        host="localhost", user="root", password=MYSQL_PASSWORD,
        database="tts_bot", charset="utf8mb4", autocommit=True
    )


def extract_answer(snapshot: str, question: str) -> str:
    """从快照中提取 question 之后的回复内容"""
    lines = snapshot.strip().split("\n")
    marker = f"λ > {question}"

    # 找最后一次出现 marker 的位置
    start = -1
    for i in range(len(lines) - 1, -1, -1):
        if marker in lines[i]:
            start = i + 1
            break
    if start < 0:
        return ""

    # 找结尾（下一个 idle 提示符）
    end = len(lines)
    for i in range(start, len(lines)):
        s = lines[i].strip()
        if "λ >" in s and question not in lines[i]:
            end = i
            break
        if s.startswith("> What would you like to do next"):
            end = i
            break

    # 提取非系统行
    reply = []
    in_tool = False
    for line in lines[start:end]:
        s = line.strip()
        if s.startswith("I will run the following command:") or s.startswith("I'll modify"):
            in_tool = True
            continue
        if in_tool:
            if "- Completed in" in s or "Tool ran without output" in s:
                in_tool = False
            continue
        if is_system(line):
            continue
        reply.append(s[2:] if s.startswith("> ") else s)

    # 去首尾空行
    while reply and not reply[0]:
        reply.pop(0)
    while reply and not reply[-1]:
        reply.pop()

    return "\n".join(reply).strip()


def is_idle(snapshot: str) -> bool:
    """kiro-cli 是否 idle"""
    for line in reversed(snapshot.strip().split("\n")):
        s = line.strip()
        if not s:
            continue
        return "λ >" in s or s.startswith("> What would you like")
    return False


def run():
    log.info("QA Matcher 启动")
    conn = db()

    while True:
        try:
            time.sleep(POLL_INTERVAL)
            c = conn.cursor()

            # 找 pending 的问题
            c.execute("""
                SELECT id, bot_name, question, created_at
                FROM qa_pair
                WHERE status='pending'
                ORDER BY created_at ASC
            """)
            pending = c.fetchall()

            if not pending:
                c.close()
                continue

            for row in pending:
                qa_id, bot_name, question, created_at = row

                # 超时 5 分钟标记 expired
                age = time.time() - created_at.timestamp()
                if age > 300:
                    c.execute("UPDATE qa_pair SET status='expired' WHERE id=%s", (qa_id,))
                    log.info(f"[{bot_name}] Q#{qa_id} 超时: {question[:40]}")
                    continue

                # 读快照
                c.execute("SELECT content FROM terminal_snapshot WHERE bot_name=%s", (bot_name,))
                snap_row = c.fetchone()
                if not snap_row or not snap_row[0]:
                    continue

                snapshot = snap_row[0]

                # 必须 idle 才提取（说明回复完成了）
                if not is_idle(snapshot):
                    continue

                # 提取回复
                answer = extract_answer(snapshot, question)
                if not answer or len(answer) < 2:
                    continue

                # 更新
                c.execute("""
                    UPDATE qa_pair SET answer=%s, status='matched', matched_at=NOW()
                    WHERE id=%s
                """, (answer, qa_id))
                log.info(f"[{bot_name}] Q#{qa_id} 匹配成功: Q={question[:30]} A={answer[:50]}...")

            c.close()

        except pymysql.OperationalError:
            log.warning("MySQL 断开，重连...")
            try:
                conn = db()
            except:
                time.sleep(5)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error(f"错误: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run()
