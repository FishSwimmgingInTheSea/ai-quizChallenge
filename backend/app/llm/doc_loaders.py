"""知识库文档解析：pdf / docx / md / txt → 纯文本 → 智能分块。

- PDF：langchain-community 的 PyPDFLoader（pypdf 提取文字层）
- DOCX：langchain-community 的 Docx2txtLoader（docx2txt 提取正文）
- MD / TXT：本质是纯文本，直接解码（UTF-8 → GBK → UTF-16 兜底），
  不引入 unstructured 重依赖（.md 无需结构感知分块，决策已人工确认）
- 分块：RecursiveCharacterTextSplitter，分隔符兼顾中文段落与句读

Loader 需要文件路径，bytes 先落临时文件再加载（Windows 下必须先
close 再交给 Loader，避免文件占用）；用后即删。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.exceptions import DocumentParseError, InvalidInputError
from app.core.logging import get_logger

logger = get_logger(__name__)

ALLOWED_KB_EXTS = {"pdf", "docx", "md", "txt"}

# 文本兜底解码顺序：UTF-8（含 BOM）→ GBK（Windows 记事本常见）→ UTF-16
_TEXT_ENCODINGS = ("utf-8-sig", "gbk", "utf-16")

# 中文优先的分块分隔符：段落 > 换行 > 句读 > 逗号 > 空格 > 字符
_CHUNK_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]


def parse_document_to_text(filename: str, content: bytes) -> str:
    """按扩展名解析上传文档为纯文本；格式不支持 / 内容为空 / 提取失败抛业务异常。"""
    ext = Path(filename or "").suffix.lower().lstrip(".")
    if ext not in ALLOWED_KB_EXTS:
        raise InvalidInputError(
            f"仅支持 {' / '.join(sorted(ALLOWED_KB_EXTS))} 格式文档"
        )
    if not content:
        raise InvalidInputError("文档内容为空")

    if ext in ("md", "txt"):
        text = _decode_text(content)
    elif ext == "pdf":
        text = _load_pdf(content)
    else:
        text = _load_docx(content)

    if not text.strip():
        raise DocumentParseError("未从文档中提取到有效文本（扫描件/图片型文件暂不支持）")
    return text


def split_text_to_chunks(
    text: str, *, chunk_size: int = 500, chunk_overlap: int = 50
) -> list[Document]:
    """纯文本 → 分块 Document 列表（元数据由调用方按需补充）。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=_CHUNK_SEPARATORS,
    )
    chunks = splitter.split_text(text)
    return [Document(page_content=c) for c in chunks]


# ---------- 内部 ----------


def _decode_text(content: bytes) -> str:
    for encoding in _TEXT_ENCODINGS:
        try:
            return content.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    raise DocumentParseError("文本文档编码无法识别，请另存为 UTF-8 后重试") from None


def _load_pdf(content: bytes) -> str:
    from langchain_community.document_loaders import PyPDFLoader

    path = _write_temp(content, ".pdf")
    try:
        pages = PyPDFLoader(path).load()
        return "\n".join(p.page_content for p in pages)
    except Exception as exc:  # noqa: BLE001 - 一切 PDF 侧异常统一转业务异常
        logger.warning("PDF 解析失败：%s", exc)
        raise DocumentParseError("PDF 解析失败，文件可能已损坏") from exc
    finally:
        Path(path).unlink(missing_ok=True)


def _load_docx(content: bytes) -> str:
    from langchain_community.document_loaders import Docx2txtLoader

    path = _write_temp(content, ".docx")
    try:
        docs = Docx2txtLoader(path).load()
        return "\n".join(d.page_content for d in docs)
    except Exception as exc:  # noqa: BLE001 - 一切 DOCX 侧异常统一转业务异常
        logger.warning("DOCX 解析失败：%s", exc)
        raise DocumentParseError("Word 解析失败，文件可能已损坏") from exc
    finally:
        Path(path).unlink(missing_ok=True)


def _write_temp(content: bytes, suffix: str) -> str:
    """写入临时文件并返回路径（调用方负责删除）。

    Windows 下 NamedTemporaryFile 必须先 close 再交给 Loader 读取，
    故 delete=False + 手动清理。
    """
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
    return tmp.name
