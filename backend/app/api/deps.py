"""依赖提供者：服务与存储的单例注入点。

测试通过 app.dependency_overrides 覆盖这些 provider 注入 mock 生成器。
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token
from app.db.orm_models import User
from app.db.session import get_db
from app.services.auth_service import AuthService
from app.services.quiz_service import QuizService
from app.services.record_service import RecordService
from app.services.report_service import ReportService
from app.services.task_store import get_task_store, TaskStore
from app.services.user_service import UserService

# auto_error=False：缺 Token / 格式错不抛 403，交给业务统一 4010（方案 §5.5）
_bearer = HTTPBearer(auto_error=False)


@lru_cache
def get_quiz_service() -> QuizService:
    return QuizService()


@lru_cache
def get_report_service() -> ReportService:
    return ReportService()


def get_store() -> TaskStore:
    return get_task_store()


# ---------- 用户系统 ----------


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(db)


def get_record_service(db: Session = Depends(get_db)) -> RecordService:
    return RecordService(db)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """必需登录的受保护接口依赖：解析 Token 并加载当前用户（方案 §5.4）。"""
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError()
    payload = decode_token(credentials.credentials)
    sub = payload.get("sub")
    if sub is None:
        raise UnauthorizedError()
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise UnauthorizedError() from None

    user = db.get(User, user_id)
    if user is None:
        raise UnauthorizedError()
    return user
