"""业务 ID 生成。"""

from __future__ import annotations

import uuid


def _short() -> str:
    return uuid.uuid4().hex[:12]


def new_task_id() -> str:
    return f"task_{_short()}"


def new_quiz_id() -> str:
    return f"quiz_{_short()}"


def question_id(index: int) -> str:
    """题目 id：q1、q2 …（index 从 1 开始）。"""
    return f"q{index}"
