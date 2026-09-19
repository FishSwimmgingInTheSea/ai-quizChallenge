"""登录接口与鉴权依赖测试（方案 §5：批次一）。

- dev 兜底模式：多次登录复用同一账户。
- 真实模式：注入假 code2session 交换器，覆盖成功与失败映射。
- get_current_user：无 Token / 伪 Token / 有效 Token 三态。
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_auth_service, get_current_user, get_db
from app.core.config import Settings
from app.core.exceptions import UnauthorizedError, WechatLoginError
from app.core.security import create_token
from app.main import create_app
from app.services.auth_service import AuthService, DEV_OPENID


@pytest.fixture
def dev_settings() -> Settings:
    """显式 dev 模式（不读 .env，避免环境变化影响测试）。"""
    return Settings(_env_file=None)


@pytest.fixture
def auth_client(db_sessionmaker: sessionmaker, dev_settings: Settings) -> TestClient:
    app = create_app()

    def override_db():
        session = db_sessionmaker()
        try:
            yield session
        finally:
            session.close()

    def override_auth_service():
        return AuthService(db_sessionmaker(), settings=dev_settings)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_auth_service] = override_auth_service
    return TestClient(app)


# ---------- dev 兜底登录（API 级） ----------


def test_login_dev_mode_creates_user_and_returns_token(auth_client: TestClient):
    resp = auth_client.post("/api/v1/auth/login", json={"code": "any-code"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["token"]
    assert data["profile"]["nickname"] == "学习小达人"
    assert data["profile"]["avatar_url"] == ""
    assert data["profile"]["total_xp"] == 0


def test_login_dev_mode_reuses_same_account(
    auth_client: TestClient, db_sessionmaker: sessionmaker
):
    first = auth_client.post("/api/v1/auth/login", json={"code": "c1"}).json()
    second = auth_client.post("/api/v1/auth/login", json={"code": "c2"}).json()
    assert first["code"] == 0 and second["code"] == 0
    # dev 模式忽略 code 值，两次登录必须是同一账户（同一 sub）；
    # token 含 iat/exp 时间性载荷，跨秒必然不同，故解码比较 sub 而非整个 token
    import jwt as pyjwt

    from app.core.config import get_settings

    payload1 = pyjwt.decode(
        first["data"]["token"], get_settings().jwt_secret, algorithms=["HS256"]
    )
    payload2 = pyjwt.decode(
        second["data"]["token"], get_settings().jwt_secret, algorithms=["HS256"]
    )
    assert payload1["sub"] == payload2["sub"]

    from app.db.orm_models import User

    with db_sessionmaker() as session:
        users = session.query(User).all()
        assert len(users) == 1
        assert users[0].openid == DEV_OPENID


def test_login_missing_code_returns_4001(auth_client: TestClient):
    resp = auth_client.post("/api/v1/auth/login", json={})
    assert resp.json()["code"] == 4001


def test_login_blank_code_returns_4001(auth_client: TestClient):
    resp = auth_client.post("/api/v1/auth/login", json={"code": "   "})
    assert resp.json()["code"] == 4001


# ---------- 真实模式（服务级，注入假交换器，不触网） ----------


def test_login_real_mode_success(db_sessionmaker: sessionmaker):
    import jwt as pyjwt

    from app.core.config import get_settings

    settings = Settings(
        _env_file=None, wechat_appid="wx-test-appid", wechat_secret="test-secret"
    )
    service = AuthService(
        db_sessionmaker(),
        settings=settings,
        code_exchanger=lambda code: f"openid-{code}",
    )
    result = service.login("code-123")
    assert result.profile.nickname == "学习小达人"
    # create_token 用全局 settings 签发，验证 sub 即可
    payload = pyjwt.decode(
        result.token, get_settings().jwt_secret, algorithms=["HS256"]
    )
    assert payload["sub"] == "1"

    # 再次登录（不同 code -> 不同 openid）应创建第二个用户
    result2 = service.login("code-456")
    payload2 = pyjwt.decode(
        result2.token, get_settings().jwt_secret, algorithms=["HS256"]
    )
    assert payload2["sub"] == "2"


def test_login_real_mode_exchange_failure_maps_4011(
    db_sessionmaker: sessionmaker,
):
    def boom(code: str) -> str:
        raise WechatLoginError()

    settings = Settings(
        _env_file=None, wechat_appid="wx-test-appid", wechat_secret="test-secret"
    )
    service = AuthService(
        db_sessionmaker(), settings=settings, code_exchanger=boom
    )
    with pytest.raises(WechatLoginError):
        service.login("bad-code")


def test_wechat_login_error_code():
    assert WechatLoginError.code == 4011
    assert WechatLoginError.message == "微信登录失败，请重试"


# ---------- get_current_user 鉴权依赖（挂最小测试 App） ----------


@pytest.fixture
def guard_app(db_sessionmaker: sessionmaker):
    from fastapi import Request
    from fastapi.responses import JSONResponse

    from app.api.response import fail
    from app.core.exceptions import AppException

    app = FastAPI()

    # 与 main.py 相同的异常处理（统一 200 + 业务 code）
    @app.exception_handler(AppException)
    async def _handler(_: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=fail(exc.code, exc.message))

    def override_db():
        session = db_sessionmaker()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db

    @app.get("/whoami")
    def whoami(user=Depends(get_current_user)) -> dict:
        return {"id": user.id, "openid": user.openid}

    return app


def _create_user(db_sessionmaker: sessionmaker) -> int:
    from app.db.orm_models import User

    with db_sessionmaker() as session:
        user = User(openid="openid-guard-test")
        session.add(user)
        session.commit()
        return user.id


def test_current_user_without_token_returns_4010(guard_app: FastAPI):
    client = TestClient(guard_app)
    resp = client.get("/whoami")
    body = resp.json()
    assert body["code"] == 4010


def test_current_user_with_garbage_token_returns_4010(guard_app: FastAPI):
    client = TestClient(guard_app)
    resp = client.get("/whoami", headers={"Authorization": "Bearer garbage"})
    body = resp.json()
    assert body["code"] == 4010


def test_current_user_with_valid_token_returns_user(
    guard_app: FastAPI, db_sessionmaker: sessionmaker
):
    uid = _create_user(db_sessionmaker)
    token = create_token(uid)
    client = TestClient(guard_app)
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"id": uid, "openid": "openid-guard-test"}


def test_current_user_with_unknown_user_returns_4010(
    guard_app: FastAPI,
):
    token = create_token(99999)  # 不存在的用户
    client = TestClient(guard_app)
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["code"] == 4010
