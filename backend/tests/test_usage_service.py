"""每人每日生图配额计数测试（question-images 任务 4.1）：内存 SQLite。"""

from __future__ import annotations

from datetime import date

from app.core.config import Settings
from app.services.usage_service import UsageService


def _settings(limit: int = 3) -> Settings:
    return Settings(image_daily_limit=limit)


def test_配额内计数递增(db_sessionmaker):
    svc = UsageService(db_sessionmaker, settings=_settings(3))
    assert svc.has_quota(1) is True
    assert svc.try_consume(1) is True
    assert svc.get_usage(1) == 1
    assert svc.try_consume(1) is True
    assert svc.get_usage(1) == 2


def test_达到上限后拒绝且不超发(db_sessionmaker):
    svc = UsageService(db_sessionmaker, settings=_settings(3))
    results = [svc.try_consume(1) for _ in range(5)]
    assert results == [True, True, True, False, False]
    assert svc.get_usage(1) == 3
    assert svc.has_quota(1) is False


def test_跨自然日配额恢复(db_sessionmaker):
    svc = UsageService(db_sessionmaker, settings=_settings(2))
    d1, d2 = date(2026, 9, 21), date(2026, 9, 22)
    assert svc.try_consume(1, day=d1) is True
    assert svc.try_consume(1, day=d1) is True
    assert svc.try_consume(1, day=d1) is False
    # 次日按新日期重新计数
    assert svc.try_consume(1, day=d2) is True
    assert svc.get_usage(1, day=d2) == 1
    assert svc.get_usage(1, day=d1) == 2


def test_不同用户配额相互独立(db_sessionmaker):
    svc = UsageService(db_sessionmaker, settings=_settings(1))
    assert svc.try_consume(1) is True
    assert svc.try_consume(2) is True  # 用户 2 不受用户 1 影响
    assert svc.try_consume(1) is False
    assert svc.get_usage(2) == 1


def test_limit为零直接拒绝(db_sessionmaker):
    svc = UsageService(db_sessionmaker, settings=_settings(0))
    assert svc.has_quota(1) is False
    assert svc.try_consume(1) is False
    assert svc.get_usage(1) == 0
