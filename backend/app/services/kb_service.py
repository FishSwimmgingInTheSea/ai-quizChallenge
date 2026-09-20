"""知识库应用服务：文档上传受理、后台解析向量化、列表/详情/删除。

- create_* 为请求内同步操作（校验 + 建行 + 落盘原始文件）；
- process_document 为后台任务（BackgroundTasks 调度，响应返回后执行），
  内部自建数据库会话（请求级 Session 届时已关闭），并把同步解析/嵌入
  工作留在工作线程（FastAPI 对同步 background task 自动走线程池）；
- 向量本体在 Chroma（KbStore），MySQL 只存元信息与状态机。
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    InvalidInputError,
    KbDocumentNotFoundError,
)
from app.core.logging import get_logger
from app.db.orm_models import KbDocument
from app.llm.doc_loaders import ALLOWED_KB_EXTS, parse_document_to_text, split_text_to_chunks
from app.models.kb import KbDocumentItem, KbDocumentPage, KbUploadResult
from app.services.kb_store import KbStore

logger = get_logger(__name__)


class KbService:
    def __init__(
        self,
        db: Session,
        kb_store: KbStore,
        *,
        settings: Settings | None = None,
    ) -> None:
        self._db = db
        self._store = kb_store
        self._settings = settings or get_settings()

    # ---------- 上传受理（请求内同步） ----------

    def create_document(
        self, user_id: int, filename: str, content: bytes
    ) -> KbUploadResult:
        """校验并受理上传：写 MySQL（processing）+ 落盘原始文件；解析入库由后台任务完成。"""
        settings = self._settings
        if not settings.kb_enabled:
            raise InvalidInputError("知识库功能暂未开放")
        if not settings.dashscope_api_key:
            raise InvalidInputError("知识库尚未配置向量模型，请联系管理员开通")

        ext = Path(filename or "").suffix.lower().lstrip(".")
        if ext not in ALLOWED_KB_EXTS:
            raise InvalidInputError(
                f"仅支持 {' / '.join(sorted(ALLOWED_KB_EXTS))} 格式文档"
            )
        if not content:
            raise InvalidInputError("文档内容为空")
        max_bytes = settings.kb_max_file_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise InvalidInputError(f"文档大小不能超过 {settings.kb_max_file_mb}MB")

        safe_name = (Path(filename).name or f"document.{ext}")[:200]
        doc = KbDocument(
            user_id=user_id,
            filename=safe_name,
            doc_type=ext,
            file_size=len(content),
            status="processing",
        )
        self._db.add(doc)
        self._db.commit()

        self._raw_path(user_id, doc.id, ext).parent.mkdir(parents=True, exist_ok=True)
        self._raw_path(user_id, doc.id, ext).write_bytes(content)
        logger.info(
            "用户 %s 上传知识库文档：%s（%d 字节，doc_id=%s）",
            user_id,
            safe_name,
            len(content),
            doc.id,
        )
        return KbUploadResult(doc_id=doc.id, status="processing")

    # ---------- 后台处理（BackgroundTasks 调度） ----------

    def process_document(self, user_id: int, doc_id: int) -> None:
        """同步后台任务：解析 → 分块 → 向量入库 → 状态机落库；绝不抛异常。

        请求级 Session 在响应返回后已关闭，这里自建会话（复用同一 engine）。
        """
        factory = sessionmaker(bind=self._db.get_bind(), expire_on_commit=False)
        with factory() as db:
            doc = db.get(KbDocument, doc_id)
            if doc is None or doc.user_id != user_id or doc.status != "processing":
                return
            try:
                content = self._raw_path(user_id, doc_id, doc.doc_type).read_bytes()
                text = parse_document_to_text(doc.filename, content)
                chunks = split_text_to_chunks(
                    text,
                    chunk_size=self._settings.kb_chunk_size,
                    chunk_overlap=self._settings.kb_chunk_overlap,
                )
                self._store.add_chunks(user_id, doc_id, doc.filename, chunks)
                doc.char_count = len(text)
                doc.chunk_count = len(chunks)
                doc.status = "ready"
                doc.error = ""
                logger.info(
                    "知识库文档 %s 处理完成：%d 字符 / %d 块",
                    doc_id,
                    doc.char_count,
                    doc.chunk_count,
                )
            except Exception as exc:  # noqa: BLE001 - 状态机兜底，不向上抛
                doc.status = "failed"
                doc.error = str(exc)[:255]
                logger.warning("知识库文档 %s 处理失败：%s", doc_id, exc)
            db.commit()

    # ---------- 查询 / 删除 ----------

    def list_documents(
        self, user_id: int, limit: int = 20, offset: int = 0
    ) -> KbDocumentPage:
        """当前用户的知识库文档列表，created_at 倒序（同秒时 id 兑底）。"""
        stmt = (
            select(KbDocument)
            .where(KbDocument.user_id == user_id)
            .order_by(KbDocument.created_at.desc(), KbDocument.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = self._db.scalars(stmt).all()
        total = (
            self._db.scalar(
                select(func.count())
                .select_from(KbDocument)
                .where(KbDocument.user_id == user_id)
            )
            or 0
        )
        return KbDocumentPage(
            total=total, documents=[self._to_item(r) for r in rows]
        )

    def get_document(self, user_id: int, doc_id: int) -> KbDocumentItem:
        return self._to_item(self._require_doc(user_id, doc_id))

    def delete_document(self, user_id: int, doc_id: int) -> None:
        """删除文档：Chroma 向量 + 原始文件 + MySQL 记录（三者幂等清理）。"""
        doc = self._require_doc(user_id, doc_id)
        self._store.delete_document(user_id, doc_id)
        self._raw_path(user_id, doc_id, doc.doc_type).unlink(missing_ok=True)
        self._db.delete(doc)
        self._db.commit()
        logger.info("用户 %s 删除知识库文档 %s", user_id, doc_id)

    def get_ready_doc_ids(self, user_id: int, doc_ids: list[int]) -> list[int]:
        """出题前校验：文档须全部属于本人且 ready；否则 4001。"""
        if not doc_ids:
            return []
        rows = self._db.scalars(
            select(KbDocument).where(
                KbDocument.user_id == user_id,
                KbDocument.id.in_(doc_ids),
                KbDocument.status == "ready",
            )
        ).all()
        ready = {r.id for r in rows}
        if any(i not in ready for i in doc_ids):
            raise InvalidInputError("选中的知识库文档不存在、不属于你或还未处理完成")
        return list(doc_ids)

    # ---------- 内部 ----------

    def _require_doc(self, user_id: int, doc_id: int) -> KbDocument:
        doc = self._db.get(KbDocument, doc_id)
        if doc is None or doc.user_id != user_id:
            raise KbDocumentNotFoundError()
        return doc

    def _raw_path(self, user_id: int, doc_id: int, ext: str) -> Path:
        return (
            Path(self._settings.upload_dir) / "kb" / str(user_id) / f"{doc_id}.{ext}"
        )

    @staticmethod
    def _to_item(doc: KbDocument) -> KbDocumentItem:
        return KbDocumentItem(
            doc_id=doc.id,
            filename=doc.filename,
            doc_type=doc.doc_type,
            file_size=doc.file_size,
            char_count=doc.char_count,
            chunk_count=doc.chunk_count,
            status=doc.status,  # type: ignore[arg-type]
            error=doc.error or "",
            created_at=doc.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        )
