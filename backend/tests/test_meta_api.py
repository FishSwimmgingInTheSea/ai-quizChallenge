"""元信息接口契约测试（meta/features）：前端配图入口按系统级有效值显隐。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_image_service
from app.core.config import Settings
from app.main import create_app
from app.services.image_service import ImageService


class _Gen:
    async def generate(self, prompt: str) -> bytes | None:
        return None


class _Store:
    def __init__(self, available: bool) -> None:
        self._available = available

    @property
    def is_available(self) -> bool:
        return self._available

    def upload(self, data: bytes, key: str) -> str | None:
        return None


class _Usage:
    def has_quota(self, *args, **kwargs) -> bool:
        return True

    def try_consume(self, *args, **kwargs) -> bool:
        return True


def _settings(**over) -> Settings:
    base = dict(
        image_gen_enabled=True,
        dashscope_api_key="sk-test",
        cos_secret_id="id",
        cos_secret_key="key",
        cos_bucket="b-123",
        cos_region="ap-guangzhou",
    )
    base.update(over)
    return Settings(**base)


def _client(service: ImageService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_image_service] = lambda: service
    return TestClient(app)


def _flag(client: TestClient) -> bool:
    resp = client.get("/api/v1/meta/features")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    return body["data"]["image_gen_enabled"]


def test_features_全配置返回真():
    svc = ImageService(_settings(), generator=_Gen(), store=_Store(True), usage=_Usage())
    assert _flag(_client(svc)) is True


def test_features_总开关关闭返回假():
    svc = ImageService(
        _settings(image_gen_enabled=False), generator=_Gen(), store=_Store(True), usage=_Usage()
    )
    assert _flag(_client(svc)) is False


def test_features_缺百炼密钥返回假():
    svc = ImageService(
        _settings(dashscope_api_key=""), generator=_Gen(), store=_Store(True), usage=_Usage()
    )
    assert _flag(_client(svc)) is False


def test_features_缺COS凭据返回假():
    svc = ImageService(_settings(), generator=_Gen(), store=_Store(False), usage=_Usage())
    assert _flag(_client(svc)) is False


def test_features_免登录可访问():
    # 公开接口：不带 Token 也不得报 4010
    svc = ImageService(_settings(), generator=_Gen(), store=_Store(True), usage=_Usage())
    resp = _client(svc).get("/api/v1/meta/features")
    assert resp.json()["code"] == 0
