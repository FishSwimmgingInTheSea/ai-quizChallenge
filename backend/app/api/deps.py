"""依赖提供者：服务与存储的单例注入点。

测试通过 app.dependency_overrides 覆盖这些 provider 注入 mock 生成器。
"""

from __future__ import annotations

from functools import lru_cache

from app.services.quiz_service import QuizService
from app.services.report_service import ReportService
from app.services.task_store import get_task_store, TaskStore


@lru_cache
def get_quiz_service() -> QuizService:
    return QuizService()


@lru_cache
def get_report_service() -> ReportService:
    return ReportService()


def get_store() -> TaskStore:
    return get_task_store()
