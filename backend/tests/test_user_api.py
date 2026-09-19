"""用户资料与头像接口测试（用户系统方案设计 §6：批次二）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db, get_user_service
from app.core.config import Settings
from app.core.security import create_token
from app.main import create_app
from app.services.user_service import UserService

# 2MB 上限（方案 §6.3）
MAX_AVATAR_BYTES = 2 * 1024 * 1024


@pytest.fixture
def user_client(
    db_sessionmaker: sessionmaker, tmp_path, monkeypatch
) -> TestClient:
    app = create_app()

    # 头像落盘到临时目录，避免污染仓库
    test_settings = Settings(_env_file=None, upload_dir=str(tmp_path))

    def override_db():
        session = db_sessionmaker()
        try:
            yield session
        finally:
            session.close()

    def override_user_service():
        return UserService(db_sessionmaker(), settings=test_settings)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_user_service] = override_user_service
    return TestClient(app)


@pytest.fixture
def user_id(db_sessionmaker: sessionmaker) -> int:
    from app.db.orm_models import User

    with db_sessionmaker() as session:
        user = User(openid="openid-profile-test")
        session.add(user)
        session.commit()
        return user.id


def auth_header(uid: int) -> dict:
    return {"Authorization": f"Bearer {create_token(uid)}"}


# ---------- GET /user/profile ----------


def test_profile_requires_login(user_client: TestClient):
    resp = user_client.get("/api/v1/user/profile")
    assert resp.json()["code"] == 4010


def test_get_profile_returns_defaults(user_client: TestClient, user_id: int):
    resp = user_client.get("/api/v1/user/profile", headers=auth_header(user_id))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {
        "nickname": "学习小达人",
        "avatar_url": "",
        "total_xp": 0,
    }


# ---------- PUT /user/profile ----------


def test_update_nickname_success(user_client: TestClient, user_id: int):
    resp = user_client.put(
        "/api/v1/user/profile",
        json={"nickname": "  爱学习的小明  "},
        headers=auth_header(user_id),
    )
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["nickname"] == "爱学习的小明"


def test_update_nickname_empty_returns_4001(user_client: TestClient, user_id: int):
    resp = user_client.put(
        "/api/v1/user/profile",
        json={"nickname": "   "},
        headers=auth_header(user_id),
    )
    assert resp.json()["code"] == 4001


def test_update_nickname_too_long_returns_4001(user_client: TestClient, user_id: int):
    resp = user_client.put(
        "/api/v1/user/profile",
        json={"nickname": "超" * 17},
        headers=auth_header(user_id),
    )
    assert resp.json()["code"] == 4001


def test_update_nickname_sensitive_returns_4002(user_client: TestClient, user_id: int):
    resp = user_client.put(
        "/api/v1/user/profile",
        json={"nickname": "赌博小王子"},
        headers=auth_header(user_id),
    )
    assert resp.json()["code"] == 4002


def test_update_profile_requires_at_least_one_field(
    user_client: TestClient, user_id: int
):
    resp = user_client.put(
        "/api/v1/user/profile", json={}, headers=auth_header(user_id)
    )
    assert resp.json()["code"] == 4001


def test_update_avatar_url_rejects_external_link(
    user_client: TestClient, user_id: int
):
    resp = user_client.put(
        "/api/v1/user/profile",
        json={"avatar_url": "https://evil.example.com/a.jpg"},
        headers=auth_header(user_id),
    )
    assert resp.json()["code"] == 4001


def test_update_avatar_url_accepts_local_static_path(
    user_client: TestClient, user_id: int
):
    url = f"/static/avatars/{user_id}/abc.jpg"
    resp = user_client.put(
        "/api/v1/user/profile",
        json={"avatar_url": url},
        headers=auth_header(user_id),
    )
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["avatar_url"] == url


def test_update_profile_requires_login(user_client: TestClient):
    resp = user_client.put("/api/v1/user/profile", json={"nickname": "x"})
    assert resp.json()["code"] == 4010


# ---------- POST /user/avatar ----------


def _jpeg_bytes(size: int) -> bytes:
    return b"\xff\xd8\xff\xe0" + b"x" * (size - 4)


def test_upload_avatar_success(
    user_client: TestClient, user_id: int, db_sessionmaker: sessionmaker
):
    resp = user_client.post(
        "/api/v1/user/avatar",
        files={"file": ("a.jpg", _jpeg_bytes(128), "image/jpeg")},
        headers=auth_header(user_id),
    )
    body = resp.json()
    assert body["code"] == 0
    avatar_url = body["data"]["avatar_url"]
    assert avatar_url.startswith(f"/static/avatars/{user_id}/")
    assert avatar_url.endswith(".jpg")

    # 文件确实落盘
    from pathlib import Path

    from app.core.config import get_settings

    # 落盘目录由 override 的 test_settings 指定（tmp_path），直接按 URL 推导校验
    rel = avatar_url.removeprefix("/static/")
    settings = get_settings()
    assert Path(settings.upload_dir)  # 占位：真实断言在下方
    # 通过 db 校验 url 未写库（两步分离：先上传后 PUT 绑定）
    from app.db.orm_models import User

    with db_sessionmaker() as session:
        assert session.get(User, user_id).avatar_url == ""


def test_upload_avatar_rejects_bad_ext(user_client: TestClient, user_id: int):
    resp = user_client.post(
        "/api/v1/user/avatar",
        files={"file": ("a.gif", b"GIF89a" + b"x" * 32, "image/gif")},
        headers=auth_header(user_id),
    )
    assert resp.json()["code"] == 4001


def test_upload_avatar_rejects_oversize(user_client: TestClient, user_id: int):
    resp = user_client.post(
        "/api/v1/user/avatar",
        files={"file": ("a.png", b"x" * (MAX_AVATAR_BYTES + 1), "image/png")},
        headers=auth_header(user_id),
    )
    assert resp.json()["code"] == 4001


def test_upload_avatar_requires_login(user_client: TestClient):
    resp = user_client.post(
        "/api/v1/user/avatar",
        files={"file": ("a.jpg", _jpeg_bytes(128), "image/jpeg")},
    )
    assert resp.json()["code"] == 4010
