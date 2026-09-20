"""KbService 测试：真实 SQLite 内存库 + 真实 Chroma（tmp_path）+ fake embedding。

覆盖：上传校验与受理、后台处理状态机（ready/failed）、列表/详情/删除、
出题前的就绪文档校验；全程不触碰百炼/DeepSeek。
"""

from __future__ import annotations

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.exceptions import InvalidInputError, KbDocumentNotFoundError
from app.db.orm_models import KbDocument, User
from app.services.kb_service import KbService
from app.services.kb_store import KbStore
from tests.test_doc_loaders import make_pdf_bytes


@pytest.fixture
def kb_settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        upload_dir=str(tmp_path / "uploads"),
        kb_persist_dir=str(tmp_path / "kb_data"),
        kb_enabled=True,
        dashscope_api_key="sk-test-dashscope",
        kb_max_file_mb=1,
        kb_chunk_size=500,
        kb_chunk_overlap=50,
    )


@pytest.fixture
def kb_store(kb_settings: Settings) -> KbStore:
    return KbStore(kb_settings.kb_persist_dir, DeterministicFakeEmbedding(size=16))


@pytest.fixture
def kb_service(
    db_sessionmaker: sessionmaker, kb_store: KbStore, kb_settings: Settings
) -> KbService:
    return KbService(db_sessionmaker(), kb_store, settings=kb_settings)


@pytest.fixture
def user_id(db_sessionmaker: sessionmaker) -> int:
    with db_sessionmaker() as session:
        user = User(openid="openid-kb-test")
        session.add(user)
        session.commit()
        return user.id


# ---------- 上传受理 ----------


def test_create_document_accepted(kb_service, kb_settings, user_id):
    result = kb_service.create_document(user_id, "培训手册.txt", "第一条守则".encode("utf-8"))
    assert result.status == "processing"
    assert result.doc_id > 0

    with kb_service._db:
        doc = kb_service._db.get(KbDocument, result.doc_id)
        assert doc.filename == "培训手册.txt"
        assert doc.doc_type == "txt"
        assert doc.file_size > 0
        assert doc.status == "processing"

    # 原始文件落盘 uploads/kb/{user_id}/{doc_id}.txt
    raw = (
        __import__("pathlib").Path(kb_settings.upload_dir)
        / "kb"
        / str(user_id)
        / f"{result.doc_id}.txt"
    )
    assert raw.read_bytes() == "第一条守则".encode("utf-8")


def test_create_rejects_bad_ext(kb_service, user_id):
    with pytest.raises(InvalidInputError):
        kb_service.create_document(user_id, "virus.exe", b"MZ")


def test_create_rejects_empty_content(kb_service, user_id):
    with pytest.raises(InvalidInputError):
        kb_service.create_document(user_id, "empty.txt", b"")


def test_create_rejects_oversize(kb_service, user_id):
    with pytest.raises(InvalidInputError):
        kb_service.create_document(user_id, "big.txt", b"x" * (1024 * 1024 + 1))


def test_create_rejects_when_disabled(kb_service, kb_settings, user_id):
    kb_settings.kb_enabled = False
    with pytest.raises(InvalidInputError):
        kb_service.create_document(user_id, "a.txt", "内容".encode("utf-8"))


def test_create_rejects_when_no_embedding_key(kb_service, kb_settings, user_id):
    kb_settings.dashscope_api_key = ""
    with pytest.raises(InvalidInputError):
        kb_service.create_document(user_id, "a.txt", "内容".encode("utf-8"))


def test_create_sanitizes_filename(kb_service, user_id):
    """携带路径的文件名只保留纯名。"""
    result = kb_service.create_document(user_id, "C:\\evil\\..\\培训.md", "内容".encode("utf-8"))
    with kb_service._db:
        doc = kb_service._db.get(KbDocument, result.doc_id)
        assert doc.filename == "培训.md"
        assert ".." not in doc.filename


# ---------- 后台处理状态机 ----------


def test_process_document_ready(kb_service, kb_store, user_id):
    content = "\n\n".join(f"第 {i} 条守则：企业知识库要点 {i}。" for i in range(1, 30))
    result = kb_service.create_document(user_id, "handbook.txt", content.encode("utf-8"))

    kb_service.process_document(user_id, result.doc_id)

    with kb_service._db:
        doc = kb_service._db.get(KbDocument, result.doc_id)
        assert doc.status == "ready"
        assert doc.error == ""
        assert doc.char_count > 0
        assert doc.chunk_count > 1

    # 向量真实入库可检索
    hits = kb_store.search(user_id, "第 3 条守则：企业知识库要点 3。", k=1)
    assert hits and hits[0].metadata["doc_id"] == result.doc_id


def test_process_document_real_pdf(kb_service, user_id):
    result = kb_service.create_document(user_id, "handbook.pdf", make_pdf_bytes("PDF KB Rule One"))
    kb_service.process_document(user_id, result.doc_id)
    with kb_service._db:
        doc = kb_service._db.get(KbDocument, result.doc_id)
        assert doc.status == "ready"


def test_process_document_parse_failure(kb_service, user_id):
    result = kb_service.create_document(user_id, "broken.pdf", b"%PDF-1.4 not a pdf" * 20)
    kb_service.process_document(user_id, result.doc_id)
    with kb_service._db:
        doc = kb_service._db.get(KbDocument, result.doc_id)
        assert doc.status == "failed"
        assert doc.error  # 具体原因
        assert doc.chunk_count == 0


def test_process_document_missing_row(kb_service, user_id):
    """行不存在 / 非本人 / 非 processing：静默跳过不抛错。"""
    kb_service.process_document(user_id, 999999)
    kb_service.process_document(user_id + 1, 1)  # 越权调用直接忽略


def test_process_document_not_reentrant(kb_service, kb_settings, user_id):
    """重复处理同一文档（状态已 ready）不再执行。"""
    result = kb_service.create_document(user_id, "once.txt", "只处理一次的内容".encode("utf-8"))
    kb_service.process_document(user_id, result.doc_id)
    with kb_service._db:
        doc = kb_service._db.get(KbDocument, result.doc_id)
        before = doc.chunk_count
    kb_service.process_document(user_id, result.doc_id)  # 已 ready，跳过
    with kb_service._db:
        doc = kb_service._db.get(KbDocument, result.doc_id)
        assert doc.chunk_count == before


# ---------- 列表 / 详情 ----------


def test_list_documents_pagination(kb_service, user_id):
    for i in range(3):
        kb_service.create_document(user_id, f"doc{i}.txt", f"内容 {i}".encode("utf-8"))
    page = kb_service.list_documents(user_id, limit=2, offset=0)
    assert page.total == 3
    assert len(page.documents) == 2
    page2 = kb_service.list_documents(user_id, limit=2, offset=2)
    assert len(page2.documents) == 1


def test_list_documents_user_isolation(kb_service, user_id):
    kb_service.create_document(user_id, "mine.txt", b"mine")
    page = kb_service.list_documents(user_id + 100, limit=10, offset=0)
    assert page.total == 0


def test_get_document(kb_service, user_id):
    result = kb_service.create_document(user_id, "detail.txt", "详情内容".encode("utf-8"))
    item = kb_service.get_document(user_id, result.doc_id)
    assert item.doc_id == result.doc_id
    assert item.filename == "detail.txt"
    assert item.status == "processing"


def test_get_document_not_found(kb_service, user_id):
    with pytest.raises(KbDocumentNotFoundError):
        kb_service.get_document(user_id, 12345)


def test_get_document_other_users(kb_service, user_id):
    result = kb_service.create_document(user_id, "secret.txt", b"secret")
    with pytest.raises(KbDocumentNotFoundError):
        kb_service.get_document(user_id + 100, result.doc_id)


# ---------- 删除 ----------


def test_delete_document(kb_service, kb_store, kb_settings, user_id):
    result = kb_service.create_document(user_id, "del.txt", "待删除知识内容".encode("utf-8"))
    kb_service.process_document(user_id, result.doc_id)

    kb_service.delete_document(user_id, result.doc_id)

    with kb_service._db:
        assert kb_service._db.get(KbDocument, result.doc_id) is None
    assert kb_store.search(user_id, "待删除知识内容", k=3) == []
    raw = (
        __import__("pathlib").Path(kb_settings.upload_dir)
        / "kb"
        / str(user_id)
        / f"{result.doc_id}.txt"
    )
    assert not raw.exists()


def test_delete_document_not_found(kb_service, user_id):
    with pytest.raises(KbDocumentNotFoundError):
        kb_service.delete_document(user_id, 12345)


# ---------- 出题前的就绪校验 ----------


def test_get_ready_doc_ids_all_ready(kb_service, user_id):
    ids = []
    for i in range(2):
        r = kb_service.create_document(user_id, f"ok{i}.txt", f"就绪内容 {i}".encode("utf-8"))
        kb_service.process_document(user_id, r.doc_id)
        ids.append(r.doc_id)
    assert kb_service.get_ready_doc_ids(user_id, ids) == ids


def test_get_ready_doc_ids_rejects_processing(kb_service, user_id):
    r = kb_service.create_document(user_id, "half.txt", "还没处理完".encode("utf-8"))
    with pytest.raises(InvalidInputError):
        kb_service.get_ready_doc_ids(user_id, [r.doc_id])


def test_get_ready_doc_ids_rejects_missing_or_foreign(kb_service, user_id):
    with pytest.raises(InvalidInputError):
        kb_service.get_ready_doc_ids(user_id, [999999])
    r = kb_service.create_document(user_id, "mine.txt", "内容".encode("utf-8"))
    with pytest.raises(InvalidInputError):
        kb_service.get_ready_doc_ids(user_id + 100, [r.doc_id])
