"""每人每日生图配额计数服务（question-images D3）。

DB 支撑、跨重启持久；(user_id, usage_date) 唯一行，count 原子自增。
`try_consume` 用「带 count<limit 守卫的 UPDATE」保证并发不超发：
InnoDB/SQLite 均在写时对行加锁并重估 WHERE，故第二个并发事务在额度
耗尽时 rowcount=0，天然拒绝。行不存在时回退 INSERT count=1，唯一键
冲突（并发插入）再重试一次守卫 UPDATE。

在后台出题任务中被调用（无请求级 Session），故自建会话；测试注入
内存 SQLite 的 sessionmaker。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.orm_models import ImageGenUsage
from app.db.session import get_session_factory

logger = get_logger(__name__)


class UsageService:
    def __init__(
        self,
        session_factory: sessionmaker | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self._factory = session_factory or get_session_factory()
        self._settings = settings or get_settings()

    @property
    def limit(self) -> int:
        return self._settings.image_daily_limit

    def get_usage(self, user_id: int, *, day: date | None = None) -> int:
        """当日已生成配图张数（无记录为 0）。"""
        day = day or date.today()
        with self._factory() as db:
            row = db.scalar(
                select(ImageGenUsage.count).where(
                    ImageGenUsage.user_id == user_id,
                    ImageGenUsage.usage_date == day,
                )
            )
            return int(row or 0)

    def has_quota(self, user_id: int, *, day: date | None = None) -> bool:
        """当日是否还有剩余配额（仅预判，不消费）。"""
        if self.limit < 1:
            return False
        return self.get_usage(user_id, day=day) < self.limit

    def try_consume(self, user_id: int, *, day: date | None = None) -> bool:
        """尝试消费一个配额：成功自增并返回 True；已达上限返回 False。

        仅在实际生图成功后调用（生图失败不消耗额度）。
        """
        if self.limit < 1:
            return False
        day = day or date.today()
        with self._factory() as db:
            # 1) 带守卫的原子自增：行存在且 count<limit 才成功
            if self._guarded_incr(db, user_id, day):
                return True
            # 2) rowcount=0：可能行不存在，或已达上限
            exists = db.scalar(
                select(ImageGenUsage.id).where(
                    ImageGenUsage.user_id == user_id,
                    ImageGenUsage.usage_date == day,
                )
            )
            if exists is not None:
                return False  # 行存在但守卫失败 => 已达上限
            # 3) 行不存在：插入 count=1
            try:
                db.add(ImageGenUsage(user_id=user_id, usage_date=day, count=1))
                db.commit()
                return True
            except IntegrityError:
                db.rollback()
                # 并发插入抢先：重试一次守卫自增
                return self._guarded_incr(db, user_id, day)

    def _guarded_incr(self, db, user_id: int, day: date) -> bool:
        res = db.execute(
            update(ImageGenUsage)
            .where(
                ImageGenUsage.user_id == user_id,
                ImageGenUsage.usage_date == day,
                ImageGenUsage.count < self.limit,
            )
            .values(count=ImageGenUsage.count + 1)
        )
        db.commit()
        return res.rowcount == 1


_default_service: UsageService | None = None


def get_usage_service() -> UsageService:
    global _default_service
    if _default_service is None:
        _default_service = UsageService()
    return _default_service
