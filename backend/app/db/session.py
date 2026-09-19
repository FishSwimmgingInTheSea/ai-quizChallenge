"""数据库连接与会话管理（用户系统方案设计 §4.1 运行时约定）。

- engine 懒创建 + lru_cache；应用 lifespan 启动时 init_db（幂等建表）、
  关闭时 dispose。
- get_db 作为 FastAPI 依赖使用，请求级 Session、用完即关。
- 测试通过 dependency_overrides[get_db] 注入 SQLite 内存会话（方案 §4.5）。
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    # pool_pre_ping：连接失效自动重连；SQLite 下无连接池副作用
    return create_engine(settings.database_url, pool_pre_ping=True)


def get_session_factory() -> sessionmaker:
    # expire_on_commit=False：提交后对象属性仍可读（便于返回响应数据）
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """请求级会话依赖。"""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """幂等建表（checkfirst），与 .env「启动后自动建表」约定一致。"""
    import app.db.orm_models  # noqa: F401  确保模型注册

    from app.db.base import Base

    Base.metadata.create_all(bind=get_engine())


def dispose_engine() -> None:
    """应用关闭时释放连接池。"""
    get_engine().dispose()
    get_engine.cache_clear()
