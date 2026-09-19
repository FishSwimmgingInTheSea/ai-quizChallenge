"""进程内出题任务状态存储（方案 §9.4.2 / §10.5 第一阶段）。

单机单进程下用一个 dict 即可，附带 TTL 清理防止内存无限增长。
将来多实例部署时可替换为 Redis，接口保持不变。
"""

from __future__ import annotations

import threading
import time

from app.core.config import get_settings
from app.models.quiz import Question, TaskState


class TaskStore:
    def __init__(self, ttl_seconds: int | None = None) -> None:
        self._data: dict[str, TaskState] = {}
        self._lock = threading.Lock()
        self._ttl = (
            ttl_seconds
            if ttl_seconds is not None
            else get_settings().task_ttl_seconds
        )

    def _purge_expired(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        expired = [
            tid
            for tid, state in self._data.items()
            if now - state.created_at > self._ttl
        ]
        for tid in expired:
            self._data.pop(tid, None)

    def create(self, state: TaskState) -> TaskState:
        with self._lock:
            self._purge_expired()
            self._data[state.task_id] = state
        return state

    def get(self, task_id: str) -> TaskState | None:
        with self._lock:
            self._purge_expired()
            return self._data.get(task_id)

    def set_status(self, task_id: str, status: str) -> None:
        with self._lock:
            state = self._data.get(task_id)
            if state:
                state.status = status  # type: ignore[assignment]

    def set_phase(self, task_id: str, phase: str) -> None:
        """更新生成阶段（researching / generating，D7）。"""
        with self._lock:
            state = self._data.get(task_id)
            if state:
                state.phase = phase

    def set_research_used(self, task_id: str, used: bool) -> None:
        """标记是否实际用上联网研究资料（D7）。"""
        with self._lock:
            state = self._data.get(task_id)
            if state:
                state.research_used = used

    def append_question(self, task_id: str, question: Question) -> None:
        with self._lock:
            state = self._data.get(task_id)
            if state:
                state.questions.append(question)
                state.generated_count = len(state.questions)

    def set_meta(self, task_id: str, quiz_id: str, title: str, summary: str) -> None:
        with self._lock:
            state = self._data.get(task_id)
            if state:
                state.quiz_id = quiz_id
                state.title = title
                state.summary = summary

    def set_error(self, task_id: str, error: str) -> None:
        with self._lock:
            state = self._data.get(task_id)
            if state:
                state.status = "failed"
                state.error = error

    def size(self) -> int:
        with self._lock:
            return len(self._data)


# 全局单例（MVP 单进程）
_default_store: TaskStore | None = None


def get_task_store() -> TaskStore:
    global _default_store
    if _default_store is None:
        _default_store = TaskStore()
    return _default_store
