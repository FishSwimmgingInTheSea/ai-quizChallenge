"""KbStore 测试：真实 Chroma 本地持久化 + 确定性 fake embedding（无网络依赖）。

覆盖：增/查/删、doc_id 元数据过滤、用户隔离、collection 不存在的容错。
"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding

from app.services.kb_store import KbStore


def make_store(tmp_path) -> KbStore:
    return KbStore(
        persist_dir=str(tmp_path / "kb_data"),
        embeddings=DeterministicFakeEmbedding(size=16),
    )


def chunks_of(doc_id: int, filename: str, *texts: str) -> list[Document]:
    return [
        Document(page_content=t, metadata={"doc_id": doc_id, "filename": filename})
        for t in texts
    ]


def test_add_and_search_exact_hit(tmp_path):
    """确定性 embedding 下，查询与 chunk 文本一致则精确命中。"""
    store = make_store(tmp_path)
    store.add_chunks(1, 10, "handbook.txt", chunks_of(10, "handbook.txt", "向量数据库基础", "检索增强生成"))

    hits = store.search(1, "向量数据库基础", k=2)
    assert any("向量数据库基础" in d.page_content for d in hits)
    assert all(d.metadata["doc_id"] == 10 for d in hits)
    assert all(d.metadata["filename"] == "handbook.txt" for d in hits)


def test_search_filter_by_doc_ids(tmp_path):
    """doc_ids 过滤：只返回指定文档集合内的 chunks。

    注：Chroma 的 where 过滤是在过滤集内取 top-k，与查询语义无关的
    chunk 也可能返回（Agent 侧自行判断相关性），断言只验证集合归属。
    """
    store = make_store(tmp_path)
    store.add_chunks(1, 10, "a.txt", chunks_of(10, "a.txt", "员工手册第一条"))
    store.add_chunks(1, 11, "b.txt", chunks_of(11, "b.txt", "客服话术第二条"))

    hits = store.search(1, "客服话术第二条", k=5, doc_ids=[10])
    assert hits != []
    assert all(d.metadata["doc_id"] == 10 for d in hits)
    hits = store.search(1, "客服话术第二条", k=5, doc_ids=[11])
    assert any("客服话术第二条" in d.page_content for d in hits)
    assert all(d.metadata["doc_id"] == 11 for d in hits)


def test_search_all_docs_when_no_filter(tmp_path):
    store = make_store(tmp_path)
    store.add_chunks(1, 10, "a.txt", chunks_of(10, "a.txt", "甲内容"))
    store.add_chunks(1, 11, "b.txt", chunks_of(11, "b.txt", "乙内容"))
    hits = store.search(1, "乙内容", k=5)
    assert any("乙内容" in d.page_content for d in hits)


def test_user_isolation(tmp_path):
    """每用户一个 collection：用户 2 检索不到用户 1 的文档。"""
    store = make_store(tmp_path)
    store.add_chunks(1, 10, "a.txt", chunks_of(10, "a.txt", "用户一的私有知识"))

    assert store.search(2, "用户一的私有知识", k=3) == []
    assert store.search(2, "用户一的私有知识", k=3, doc_ids=[10]) == []


def test_delete_document(tmp_path):
    store = make_store(tmp_path)
    store.add_chunks(1, 10, "a.txt", chunks_of(10, "a.txt", "待删除内容", "待删除内容二"))
    store.add_chunks(1, 11, "b.txt", chunks_of(11, "b.txt", "保留内容"))

    store.delete_document(1, 10)

    hits = store.search(1, "待删除内容", k=5)
    # 删除后：不再返回 doc 10 的任何 chunk（过滤集内不相关结果仍可能返回）
    assert all(d.metadata["doc_id"] != 10 for d in hits)
    assert not any("待删除内容" in d.page_content for d in hits)
    hits = store.search(1, "保留内容", k=5)
    assert any("保留内容" in d.page_content for d in hits)


def test_delete_document_never_added(tmp_path):
    """删除不存在的文档/用户 collection 不存在：静默成功（幂等）。"""
    store = make_store(tmp_path)
    store.delete_document(99, 123)  # 不应抛异常


def test_search_user_without_collection(tmp_path):
    """从未上传过的用户检索：返回空而不报错。"""
    store = make_store(tmp_path)
    assert store.search(42, "任何查询", k=3) == []


def test_persistence_across_instances(tmp_path):
    """持久化：新 KbStore 实例（同目录）可读到旧数据。"""
    store = make_store(tmp_path)
    store.add_chunks(1, 10, "a.txt", chunks_of(10, "a.txt", "重启后仍在"))

    store2 = KbStore(
        persist_dir=str(tmp_path / "kb_data"),
        embeddings=DeterministicFakeEmbedding(size=16),
    )
    hits = store2.search(1, "重启后仍在", k=3)
    assert any("重启后仍在" in d.page_content for d in hits)


# ---------- 自动出题概览取样（sample） ----------


def test_sample_returns_chunks_per_doc(tmp_path):
    store = make_store(tmp_path)
    store.add_chunks(
        1, 10, "a.txt", chunks_of(10, "a.txt", "甲一", "甲二", "甲三")
    )
    store.add_chunks(1, 11, "b.txt", chunks_of(11, "b.txt", "乙一", "乙二"))

    docs = store.sample(1, [10, 11], per_doc=2)
    # 每文档最多 per_doc 条：3 chunk 文档被截到 2 条
    assert sum(d.metadata["doc_id"] == 10 for d in docs) == 2
    assert sum(d.metadata["doc_id"] == 11 for d in docs) == 2
    assert all(d.metadata["filename"] in ("a.txt", "b.txt") for d in docs)


def test_sample_without_collection_returns_empty(tmp_path):
    store = make_store(tmp_path)
    assert store.sample(42, [1, 2]) == []


def test_sample_missing_doc_ignored(tmp_path):
    store = make_store(tmp_path)
    store.add_chunks(1, 10, "a.txt", chunks_of(10, "a.txt", "甲内容"))
    docs = store.sample(1, [10, 999])
    assert len(docs) == 1
    assert docs[0].metadata["doc_id"] == 10
