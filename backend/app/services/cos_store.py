"""腾讯云 COS 图片存储封装（question-images D4）。

公有读桶 + 默认域名：`put_object` 上传字节后用 `get_object_url` 取永久 URL。
qcloud_cos 为同步 SDK，`upload` 由调用方（image_service）经 asyncio.to_thread
下放；凭据缺失或任何异常均返回 None，由上层降级为不配图，绝不冒泡。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_KEY_PREFIX = "quiz-images"


def build_object_key(user_id: int, ext: str = "png") -> str:
    """构造对象键：quiz-images/{user_id}/{yyyymm}/{uuid}.{ext}。"""
    ext = (ext or "png").lstrip(".").lower()
    yyyymm = datetime.now().strftime("%Y%m")
    return f"{_KEY_PREFIX}/{user_id}/{yyyymm}/{uuid.uuid4().hex}.{ext}"


@runtime_checkable
class ImageStore(Protocol):
    """图片对象存储协议：上传字节换取永久 URL；不可用/失败返回 None。"""

    @property
    def is_available(self) -> bool: ...

    def upload(self, data: bytes, key: str) -> str | None: ...


class CosImageStore:
    """腾讯云 COS 图片存储（客户端惰性构建并缓存）。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = None

    @property
    def is_available(self) -> bool:
        s = self._settings
        return bool(s.cos_secret_id and s.cos_secret_key and s.cos_bucket and s.cos_region)

    def upload(self, data: bytes, key: str) -> str | None:
        """上传字节到 COS，返回公有读永久 URL；不可用/空数据/异常返回 None。"""
        if not self.is_available or not data:
            return None
        try:
            client = self._get_client()
            bucket = self._settings.cos_bucket
            client.put_object(Bucket=bucket, Body=data, Key=key)
            return client.get_object_url(Bucket=bucket, Key=key)
        except Exception as exc:  # noqa: BLE001 - 上传失败一律降级，不冒泡
            logger.warning("COS 上传失败（降级为不配图）：%s", exc)
            return None

    def _get_client(self):
        """惰性构建并缓存 CosS3Client（未启用配图时不加载 SDK）。"""
        if self._client is None:
            from qcloud_cos import CosConfig, CosS3Client

            s = self._settings
            config = CosConfig(
                Region=s.cos_region,
                SecretId=s.cos_secret_id,
                SecretKey=s.cos_secret_key,
            )
            self._client = CosS3Client(config)
        return self._client


# 全局单例（MVP 单进程）
_default_store: CosImageStore | None = None


def get_cos_store() -> CosImageStore:
    global _default_store
    if _default_store is None:
        _default_store = CosImageStore()
    return _default_store
