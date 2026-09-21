"""配图编排服务（question-images D6）：门禁判定 + 单题生图/转存/配额。

所有降级路径统一收敛为返回「不带图」，绝不向出题主流程抛异常：
- `plan(user_id)`：任务级门禁——总开关关闭 / 未登录 / 未配密钥或 COS
  凭据时不启用配图；未登录返回登录提示。
- `generate_for_question(...)`：单题路径——额度用尽返回配额提示；生图或
  上传失败仅让该题不带图；成功则消费一个配额并返回 COS 永久 URL。

配额采用「先判额度 → 生图 → 上传 → 成功后计数」：生图/上传失败不消耗
额度；并发下若计数守卫失败（额度已被抢占）则丢弃已生成图片，保证不超发。
"""

from __future__ import annotations

import asyncio
from typing import NamedTuple

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.image_gen import DashScopeImageGenerator, ImageGenerator, build_image_prompt
from app.models.quiz import Question
from app.services.cos_store import CosImageStore, ImageStore, build_object_key
from app.services.usage_service import UsageService

logger = get_logger(__name__)

# 面向用户的降级友好提示（随 TaskState.image_notice 返回）
LOGIN_NOTICE = "登录后即可为题目生成配图"
QUOTA_NOTICE = "今日配图额度已用完，明天再来吧"


class ImagePlan(NamedTuple):
    """任务级配图门禁结果。"""

    enabled: bool
    notice: str


class ImageService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        generator: ImageGenerator | None = None,
        store: ImageStore | None = None,
        usage: UsageService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._generator = generator or DashScopeImageGenerator(self._settings)
        self._store = store if store is not None else CosImageStore(self._settings)
        self._usage = usage or UsageService(settings=self._settings)

    def system_available(self) -> bool:
        """配图系统级可用性（总开关 + 百炼密钥 + COS 凭据），不含登录/配额。

        单一事实源：`plan()` 的任务级门禁与 `GET /meta/features` 暴露给
        前端的开关标志共用本判定，保证前端入口显隐与后端真实能力一致。
        """
        s = self._settings
        if not s.image_gen_enabled:
            return False
        if not s.dashscope_api_key:
            return False
        return self._store.is_available

    def plan(self, user_id: int | None) -> ImagePlan:
        """任务级门禁：判定本次出题是否尝试配图，并给出降级提示（如有）。"""
        s = self._settings
        if not s.image_gen_enabled:
            logger.info("配图总开关关闭，跳过配图")
            return ImagePlan(False, "")
        if user_id is None:
            return ImagePlan(False, LOGIN_NOTICE)
        if not self.system_available():
            logger.info("未配置百炼密钥或 COS 凭据，跳过配图")
            return ImagePlan(False, "")
        return ImagePlan(True, "")

    async def generate_for_question(
        self, question: Question, *, user_id: int
    ) -> tuple[str | None, str | None]:
        """为单题生成配图，返回 (永久URL | None, 降级提示 | None)。"""
        try:
            if not await asyncio.to_thread(self._usage.has_quota, user_id):
                return None, QUOTA_NOTICE

            prompt = build_image_prompt(
                question, max_len=self._settings.image_prompt_max_len
            )
            data = await self._generator.generate(prompt)
            if not data:
                return None, None

            key = build_object_key(user_id, "png")
            url = await asyncio.to_thread(self._store.upload, data, key)
            if not url:
                return None, None

            # 成功后才计数；并发下计数守卫失败说明额度已被抢占，丢弃图片不超发
            if not await asyncio.to_thread(self._usage.try_consume, user_id):
                return None, QUOTA_NOTICE
            return url, None
        except Exception as exc:  # noqa: BLE001 - 配图失败一律降级，不冒泡
            logger.warning("配图生成异常（降级为不配图）：%s", exc)
            return None, None


_default_service: ImageService | None = None


def get_image_service() -> ImageService:
    global _default_service
    if _default_service is None:
        _default_service = ImageService()
    return _default_service
