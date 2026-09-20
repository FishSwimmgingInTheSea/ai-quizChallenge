"""知识库文档解析测试：pdf / docx / md / txt → 纯文本，及智能分块。

PDF / DOCX 用手工构造的最小合法文件驱动真实 Loader（不 mock），
保证 PyPDFLoader / Docx2txtLoader 链路真实可用。
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.core.exceptions import DocumentParseError, InvalidInputError
from app.llm.doc_loaders import (
    ALLOWED_KB_EXTS,
    parse_document_to_text,
    split_text_to_chunks,
)


# ---------- 测试素材构造 ----------


def make_pdf_bytes(text: str) -> bytes:
    """手工构造最小单页 PDF（正文含一行文本），pypdf 可正常提取。"""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length "
        + str(len(content)).encode()
        + b" >>\nstream\n"
        + content
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF".encode()
    )
    return out.getvalue()


def make_pdf_bytes_blank() -> bytes:
    """无文字层的空白单页 PDF（模拟扫描件）。"""
    content = b"BT /F1 12 Tf 72 720 Td ET"  # Td 后无文本操作符
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length "
        + str(len(content)).encode()
        + b" >>\nstream\n"
        + content
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF".encode()
    )
    return out.getvalue()


def make_docx_bytes(*paragraphs: str) -> bytes:
    """手工构造最小 docx（docx2txt 只需 word/document.xml）。"""
    body = "".join(
        f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs
    )
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?>')
        z.writestr("word/document.xml", doc_xml)
    return buf.getvalue()


# ---------- 文本格式 ----------


def test_allowed_exts():
    assert ALLOWED_KB_EXTS == {"pdf", "docx", "md", "txt"}


def test_parse_txt_utf8():
    text = parse_document_to_text("notes.txt", "RAG 是检索增强生成".encode("utf-8"))
    assert "检索增强生成" in text


def test_parse_txt_gbk_fallback():
    """Windows 记事本常见 GBK 编码兜底。"""
    text = parse_document_to_text("notes.txt", "企业内部培训资料".encode("gbk"))
    assert "企业内部培训资料" in text


def test_parse_md_as_plain_text():
    content = "# 标题\n\n私有知识库 **要点**：向量检索。".encode("utf-8")
    text = parse_document_to_text("kb.md", content)
    assert "私有知识库" in text and "向量检索" in text


def test_parse_unsupported_ext():
    with pytest.raises(InvalidInputError):
        parse_document_to_text("virus.exe", b"MZ...")


def test_parse_empty_content():
    with pytest.raises(InvalidInputError):
        parse_document_to_text("empty.txt", b"")


def test_parse_whitespace_only_txt():
    with pytest.raises(DocumentParseError):
        parse_document_to_text("blank.txt", "   \n\t  ".encode("utf-8"))


def test_parse_undecodable_txt():
    """既非 UTF-8 也非 GBK/UTF-16 的二进制内容。

    0xff 对 UTF-8 非法、对 GBK 超出首字节范围，奇数长度对 UTF-16 非法。
    """
    with pytest.raises(DocumentParseError):
        parse_document_to_text("bad.txt", b"\xff" * 11)


# ---------- PDF ----------


def test_parse_pdf():
    text = parse_document_to_text("handbook.pdf", make_pdf_bytes("Hello KB PDF Test"))
    assert "Hello KB PDF Test" in text


def test_parse_pdf_blank_raises():
    """扫描件/图片型 PDF 无文字层：应给出可理解的错误。"""
    with pytest.raises(DocumentParseError):
        parse_document_to_text("scan.pdf", make_pdf_bytes_blank())


def test_parse_corrupted_pdf_raises():
    with pytest.raises(DocumentParseError):
        parse_document_to_text("broken.pdf", b"%PDF-1.4 this is not a real pdf" * 20)


# ---------- DOCX ----------


def test_parse_docx():
    content = make_docx_bytes("企业培训第一课", "第二条守则内容")
    text = parse_document_to_text("manual.docx", content)
    assert "企业培训第一课" in text
    assert "第二条守则内容" in text


def test_parse_docx_no_text_raises():
    with pytest.raises(DocumentParseError):
        parse_document_to_text("empty.docx", make_docx_bytes("   "))


def test_parse_corrupted_docx_raises():
    with pytest.raises(DocumentParseError):
        parse_document_to_text("broken.docx", b"PK\x03\x04 not a zip payload")


# ---------- 分块 ----------


def test_split_short_text_single_chunk():
    chunks = split_text_to_chunks("很短的知识点", chunk_size=500, chunk_overlap=50)
    assert len(chunks) == 1
    assert chunks[0].page_content == "很短的知识点"


def test_split_long_text_ordered_and_complete():
    """长文本分块有序，且关键内容不丢失。"""
    para = "这是一个关于私有知识库检索增强的知识点，包含事实与细节。" * 10  # 约 290 字
    text = "\n\n".join(para + f"（第 {i} 段）" for i in range(1, 8))
    chunks = split_text_to_chunks(text, chunk_size=500, chunk_overlap=50)
    assert len(chunks) > 1
    # 每块不超预算（RecursiveCharacterTextSplitter 允许略超，做宽松上限）
    assert all(len(c.page_content) <= 500 + 80 for c in chunks)
    joined = "".join(c.page_content for c in chunks)
    assert "（第 1 段）" in joined and "（第 7 段）" in joined
    # 有序：段落序号在拼接结果中单调出现
    first_idx = joined.find("（第 1 段）")
    last_idx = joined.rfind("（第 7 段）")
    assert first_idx < last_idx


def test_split_chunks_are_documents():
    chunks = split_text_to_chunks("内容块", chunk_size=500, chunk_overlap=50)
    assert all(c.page_content for c in chunks)
