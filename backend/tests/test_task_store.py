"""任务存储与 TTL 清理测试。"""

from __future__ import annotations

import time

from app.models.quiz import Option, Question, TaskState
from app.services.task_store import TaskStore


def _question() -> Question:
    return Question(
        id="q1",
        type="single",
        stem="题",
        options=[Option(key="A", text="a"), Option(key="B", text="b")],
        answer=["A"],
        explanation="讲解",
        knowledge_point="kp",
        difficulty="easy",
    )


def test_create_and_get():
    store = TaskStore(ttl_seconds=100)
    store.create(TaskState(task_id="t1", total=5))
    assert store.get("t1").total == 5


def test_append_question_updates_count():
    store = TaskStore(ttl_seconds=100)
    store.create(TaskState(task_id="t1", total=5))
    store.append_question("t1", _question())
    state = store.get("t1")
    assert state.generated_count == 1
    assert len(state.questions) == 1


def test_set_meta_and_error():
    store = TaskStore(ttl_seconds=100)
    store.create(TaskState(task_id="t1", total=5))
    store.set_meta("t1", "quiz_1", "标题", "摘要")
    store.set_error("t1", "boom")
    state = store.get("t1")
    assert state.quiz_id == "quiz_1"
    assert state.status == "failed"
    assert state.error == "boom"


def test_ttl_purges_expired():
    store = TaskStore(ttl_seconds=0)  # 立即过期
    old = TaskState(task_id="old", total=1)
    old.created_at = time.time() - 10
    store.create(old)
    # 触发一次带清理的读取
    assert store.get("old") is None
    assert store.size() == 0
