"""知识库接口测试（kb-rag：上传 / 列表 / 详情 / 删除）。

dependency_overrides 注入内存库 + 占位向量库，后台解析任务真实执行
（txt 解析为纯逻辑，不触碰模型与网络）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db, get_kb_service
from app.core.config import Settings
from app.core.security import create_token
from app.main import create_app
from app.services.kb_service import KbService
from tests.conftest import FakeKbStore


@pytest.fixture
def kb_client(db_sessionmaker: sessionmaker, tmp_path) -> TestClient:
    app = create_app()
    test_settings = Settings(
        _env_file=None,
        upload_dir=str(tmp_path),
        kb_enabled=True,
        dashscope_api_key="sk-test",
        kb_max_file_mb=1,
    )

    def override_db():
        session = db_sessionmaker()
        try:
            yield session
        finally:
            session.close()

    def override_kb_service():
        return KbService(db_sessionmaker(), FakeKbStore(), settings=test_settings)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_kb_service] = override_kb_service
    return TestClient(app)


@pytest.fixture
def user_id(db_sessionmaker: sessionmaker) -> int:
    from app.db.orm_models import User

    with db_sessionmaker() as session:
        user = User(openid="openid-kb-api-test")
        session.add(user)
        session.commit()
        return user.id


def auth_header(uid: int) -> dict:
    return {"Authorization": f"Bearer {create_token(uid)}"}


def upload(client: TestClient, uid: int, name: str, content: bytes, **files_kwargs):
    return client.post(
        "/api/v1/kb/documents",
        files={"file": (name, content, "application/octet-stream")},
        headers=auth_header(uid),
    )


# ---------- POST /kb/documents ----------


def test_kb_upload_requires_login(kb_client: TestClient):
    resp = kb_client.post(
        "/api/v1/kb/documents",
        files={"file": ("a.txt", "内容".encode("utf-8"), "text/plain")},
    )
    assert resp.json()["code"] == 4010


def test_kb_upload_success_then_ready(kb_client: TestClient, user_id: int):
    resp = upload(kb_client, user_id, "handbook.txt", "第一条：每日站会。".encode("utf-8"))
    body = resp.json()
    assert body["code"] == 0
    doc_id = body["data"]["doc_id"]
    assert body["data"]["status"] == "processing"

    # TestClient 返回响应前已执行后台解析任务：列表中状态就绪
    lst = kb_client.get(
        "/api/v1/kb/documents", headers=auth_header(user_id)
    ).json()
    assert lst["code"] == 0
    assert lst["data"]["total"] == 1
    doc = lst["data"]["documents"][0]
    assert doc["doc_id"] == doc_id
    assert doc["status"] == "ready"
    assert doc["filename"] == "handbook.txt"
    assert doc["chunk_count"] >= 1


def test_kb_upload_bad_ext_rejected(kb_client: TestClient, user_id: int):
    resp = upload(kb_client, user_id, "virus.exe", b"MZ...")
    assert resp.json()["code"] == 4001


def test_kb_upload_empty_rejected(kb_client: TestClient, user_id: int):
    resp = upload(kb_client, user_id, "empty.txt", b"")
    assert resp.json()["code"] == 4001


def test_kb_upload_oversize_rejected(kb_client: TestClient, user_id: int):
    resp = upload(kb_client, user_id, "big.txt", b"x" * (1024 * 1024 + 1))
    assert resp.json()["code"] == 4001


def test_kb_upload_unparseable_marks_failed(kb_client: TestClient, user_id: int):
    # 合法受理 + 后台解析失败：状态机落到 failed 而非 500
    resp = upload(kb_client, user_id, "broken.txt", b"\xff" * 11)
    assert resp.json()["code"] == 0
    lst = kb_client.get(
        "/api/v1/kb/documents", headers=auth_header(user_id)
    ).json()
    doc = lst["data"]["documents"][0]
    assert doc["status"] == "failed"
    assert doc["error"]


def test_kb_upload_disabled_rejected(db_sessionmaker, tmp_path):
    app = create_app()
    settings = Settings(
        _env_file=None, upload_dir=str(tmp_path), kb_enabled=False,
        dashscope_api_key="sk-test",
    )

    def override_db():
        session = db_sessionmaker()
        try:
            yield session
        finally:
            session.close()

    def override_kb_service():
        return KbService(db_sessionmaker(), FakeKbStore(), settings=settings)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_kb_service] = override_kb_service
    with db_sessionmaker() as session:
        from app.db.orm_models import User

        user = User(openid="openid-kb-disabled")
        session.add(user)
        session.commit()
        uid = user.id

    client = TestClient(app)
    resp = client.post(
        "/api/v1/kb/documents",
        files={"file": ("a.txt", b"hello", "text/plain")},
        headers=auth_header(uid),
    )
    assert resp.json()["code"] == 4001


def test_kb_upload_without_dashscope_key_rejected(db_sessionmaker, tmp_path):
    app = create_app()
    settings = Settings(
        _env_file=None, upload_dir=str(tmp_path),
        kb_enabled=True, dashscope_api_key="",
    )

    def override_db():
        session = db_sessionmaker()
        try:
            yield session
        finally:
            session.close()

    def override_kb_service():
        return KbService(db_sessionmaker(), FakeKbStore(), settings=settings)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_kb_service] = override_kb_service
    with db_sessionmaker() as session:
        from app.db.orm_models import User

        user = User(openid="openid-kb-nokey")
        session.add(user)
        session.commit()
        uid = user.id

    client = TestClient(app)
    resp = client.post(
        "/api/v1/kb/documents",
        files={"file": ("a.txt", b"hello", "text/plain")},
        headers=auth_header(uid),
    )
    assert resp.json()["code"] == 4001


# ---------- GET /kb/documents ----------


def test_kb_list_requires_login(kb_client: TestClient):
    resp = kb_client.get("/api/v1/kb/documents")
    assert resp.json()["code"] == 4010


def test_kb_list_scoped_to_owner(kb_client: TestClient, user_id: int, db_sessionmaker):
    with db_sessionmaker() as session:
        from app.db.orm_models import User

        other = User(openid="openid-kb-other")
        session.add(other)
        session.commit()
        other_id = other.id

    upload(kb_client, user_id, "mine.txt", b"my doc")
    upload(kb_client, other_id, "theirs.txt", b"other doc")

    mine = kb_client.get(
        "/api/v1/kb/documents", headers=auth_header(user_id)
    ).json()["data"]
    theirs = kb_client.get(
        "/api/v1/kb/documents", headers=auth_header(other_id)
    ).json()["data"]
    assert mine["total"] == 1 and mine["documents"][0]["filename"] == "mine.txt"
    assert theirs["total"] == 1 and theirs["documents"][0]["filename"] == "theirs.txt"


def test_kb_list_pagination(kb_client: TestClient, user_id: int):
    for i in range(3):
        upload(kb_client, user_id, f"doc{i}.txt", f"内容 {i}".encode("utf-8"))

    page = kb_client.get(
        "/api/v1/kb/documents",
        params={"limit": 2, "offset": 0},
        headers=auth_header(user_id),
    ).json()["data"]
    assert page["total"] == 3
    assert len(page["documents"]) == 2

    page2 = kb_client.get(
        "/api/v1/kb/documents",
        params={"limit": 2, "offset": 2},
        headers=auth_header(user_id),
    ).json()["data"]
    assert len(page2["documents"]) == 1


# ---------- GET /kb/documents/{doc_id} ----------


def test_kb_detail_requires_login(kb_client: TestClient, user_id: int):
    resp = upload(kb_client, user_id, "a.txt", b"hello")
    doc_id = resp.json()["data"]["doc_id"]
    resp = kb_client.get(f"/api/v1/kb/documents/{doc_id}")
    assert resp.json()["code"] == 4010


def test_kb_detail_success(kb_client: TestClient, user_id: int):
    resp = upload(kb_client, user_id, "notes.md", "# 标题\n正文".encode("utf-8"))
    doc_id = resp.json()["data"]["doc_id"]
    detail = kb_client.get(
        f"/api/v1/kb/documents/{doc_id}", headers=auth_header(user_id)
    ).json()
    assert detail["code"] == 0
    assert detail["data"]["doc_id"] == doc_id
    assert detail["data"]["doc_type"] == "md"
    assert detail["data"]["status"] == "ready"


def test_kb_detail_foreign_doc_404(kb_client: TestClient, user_id: int, db_sessionmaker):
    with db_sessionmaker() as session:
        from app.db.orm_models import User

        other = User(openid="openid-kb-detail-other")
        session.add(other)
        session.commit()
        other_id = other.id

    resp = upload(kb_client, other_id, "secret.txt", b"secret")
    doc_id = resp.json()["data"]["doc_id"]
    detail = kb_client.get(
        f"/api/v1/kb/documents/{doc_id}", headers=auth_header(user_id)
    ).json()
    assert detail["code"] == 4004


def test_kb_detail_unknown_doc_404(kb_client: TestClient, user_id: int):
    detail = kb_client.get(
        "/api/v1/kb/documents/99999", headers=auth_header(user_id)
    ).json()
    assert detail["code"] == 4004


# ---------- DELETE /kb/documents/{doc_id} ----------


def test_kb_delete_requires_login(kb_client: TestClient, user_id: int):
    resp = upload(kb_client, user_id, "a.txt", b"hello")
    doc_id = resp.json()["data"]["doc_id"]
    resp = kb_client.delete(f"/api/v1/kb/documents/{doc_id}")
    assert resp.json()["code"] == 4010


def test_kb_delete_success(kb_client: TestClient, user_id: int):
    resp = upload(kb_client, user_id, "a.txt", b"hello")
    doc_id = resp.json()["data"]["doc_id"]
    deleted = kb_client.delete(
        f"/api/v1/kb/documents/{doc_id}", headers=auth_header(user_id)
    ).json()
    assert deleted["code"] == 0

    lst = kb_client.get(
        "/api/v1/kb/documents", headers=auth_header(user_id)
    ).json()["data"]
    assert lst["total"] == 0

    # 删除后详情 404；重复删除幂等 404
    detail = kb_client.get(
        f"/api/v1/kb/documents/{doc_id}", headers=auth_header(user_id)
    ).json()
    assert detail["code"] == 4004
    again = kb_client.delete(
        f"/api/v1/kb/documents/{doc_id}", headers=auth_header(user_id)
    ).json()
    assert again["code"] == 4004


def test_kb_delete_foreign_doc_404(kb_client: TestClient, user_id: int, db_sessionmaker):
    with db_sessionmaker() as session:
        from app.db.orm_models import User

        other = User(openid="openid-kb-del-other")
        session.add(other)
        session.commit()
        other_id = other.id

    resp = upload(kb_client, other_id, "keep.txt", b"keep")
    doc_id = resp.json()["data"]["doc_id"]
    resp = kb_client.delete(
        f"/api/v1/kb/documents/{doc_id}", headers=auth_header(user_id)
    ).json()
    assert resp["code"] == 4004
    # 文档仍归属原主人
    detail = kb_client.get(
        f"/api/v1/kb/documents/{doc_id}", headers=auth_header(other_id)
    ).json()
    assert detail["code"] == 0
