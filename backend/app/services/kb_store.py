"""Chroma 向量库封装：每用户一个 collection，文档用 doc_id 元数据区分。

- 单一 PersistentClient 贯穿实例生命周期（同一 persist 目录必须复用
  client，否则会出现 sqlite 锁冲突）；生产经 get_kb_store() 全局单例。
- 增/查/删均通过 langchain-chroma 的 Chroma 包装（embedding 由注入的
  Embeddings 计算，不触发 Chroma 默认 ONNX 模型下载）。
- 按元数据删除走底层 collection.delete(where=...)（langchain 包装的
  delete 仅支持按 id）。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import chromadb
from chromadb.errors import NotFoundError
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.core.logging import get_logger

logger = get_logger(__name__)


class KbStore:
    """用户私有知识库向量存储（用户隔离 + 文档级元数据）。"""

    def __init__(self, persist_dir: str | Path, embeddings: Embeddings) -> None:
        self._persist_dir = str(persist_dir)
        self._embeddings = embeddings
        Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
        # 单一 client：同目录复用是 Chroma 的硬性要求（防 sqlite 锁冲突）
        self._client = chromadb.PersistentClient(path=self._persist_dir)

    @staticmethod
    def collection_name(user_id: int) -> str:
        """Chroma collection 命名：^[a-zA-Z0-9._-]{3,63}$，user_{id} 满足。"""
        return f"user_{user_id}"

    def add_chunks(
        self, user_id: int, doc_id: int, filename: str, chunks: list[Document]
    ) -> None:
        """文档分块写入用户 collection（元数据带 doc_id / filename）。"""
        if not chunks:
            return
        store = self._vectorstore(user_id)
        docs = [
            Document(
                page_content=c.page_content,
                metadata={
                    "doc_id": doc_id,
                    "filename": filename,
                    **(c.metadata or {}),
                },
            )
            for c in chunks
        ]
        ids = [f"doc{doc_id}_{i}_{uuid4().hex[:8]}" for i in range(len(docs))]
        store.add_documents(documents=docs, ids=ids)

    def search(
        self,
        user_id: int,
        query: str,
        *,
        k: int = 4,
        doc_ids: list[int] | None = None,
    ) -> list[Document]:
        """语义检索；doc_ids 非空时只在该文档集合内检索。"""
        if self._find_collection(user_id) is None:
            return []
        store = self._vectorstore(user_id)
        where: dict | None = None
        if doc_ids:
            where = {"doc_id": {"$in": list(doc_ids)}}
        try:
            return store.similarity_search(query, k=k, filter=where)
        except Exception:  # noqa: BLE001 - 检索一切异常返回空，由上层降级
            logger.warning("知识库检索失败（user=%s, doc_ids=%s）", user_id, doc_ids)
            return []

    def sample(
        self, user_id: int, doc_ids: list[int], *, per_doc: int = 2
    ) -> list[Document]:
        """按元数据取每文档开头若干 chunks（自动出题的主题概览）。

        纯 metadata 过滤读取，不触发 embedding 网络调用；顺序不保证，
        由调用方仅作内容概览使用。
        """
        collection = self._find_collection(user_id)
        if collection is None:
            return []
        docs: list[Document] = []
        for doc_id in doc_ids:
            try:
                got = collection.get(
                    where={"doc_id": doc_id},
                    limit=per_doc,
                    include=["documents", "metadatas"],
                )
            except Exception:  # noqa: BLE001 - 与 search 同风格，异常由上层降级
                logger.warning("知识库取样失败（user=%s, doc=%s）", user_id, doc_id)
                continue
            for content, meta in zip(
                got.get("documents") or [], got.get("metadatas") or []
            ):
                docs.append(Document(page_content=content, metadata=meta or {}))
        return docs

    def delete_document(self, user_id: int, doc_id: int) -> None:
        """按 doc_id 删除该文档全部 chunks（幂等，collection 不存在也静默）。"""
        collection = self._find_collection(user_id)
        if collection is None:
            return
        try:
            collection.delete(where={"doc_id": doc_id})
        except Exception:  # noqa: BLE001
            logger.warning("知识库删除失败（user=%s, doc=%s）", user_id, doc_id)

    # ---------- 内部 ----------

    def _vectorstore(self, user_id: int) -> Chroma:
        """用户 vectorstore（get_or_create，复用全局 client）。"""
        return Chroma(
            collection_name=self.collection_name(user_id),
            embedding_function=self._embeddings,
            client=self._client,
        )

    def _find_collection(self, user_id: int):
        """返回用户底层 collection；不存在返回 None。"""
        try:
            return self._client.get_collection(self.collection_name(user_id))
        except (NotFoundError, ValueError):
            return None


# 全局单例（MVP 单进程；多实例部署时按 persist_dir 分片或换服务端 Chroma）
_default_kb_store: KbStore | None = None


def get_kb_store() -> KbStore:
    global _default_kb_store
    if _default_kb_store is None:
        from app.core.config import get_settings
        from app.llm.langchain_factory import get_embeddings

        settings = get_settings()
        _default_kb_store = KbStore(
            persist_dir=settings.kb_persist_dir,
            embeddings=get_embeddings(),
        )
    return _default_kb_store
