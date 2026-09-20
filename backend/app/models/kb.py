"""知识库 DTO（对齐用户系统 DTO 风格）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

KbDocStatus = Literal["processing", "ready", "failed"]


class KbDocumentItem(BaseModel):
    """知识库文档条目（列表 / 详情 / 轮询共用）。"""

    doc_id: int
    filename: str
    doc_type: str = Field(description="pdf / docx / md / txt")
    file_size: int = Field(description="上传文件字节数")
    char_count: int = Field(default=0, description="解析后纯文本字符数（ready 后有值）")
    chunk_count: int = Field(default=0, description="向量分块数（ready 后有值）")
    status: KbDocStatus
    error: str = Field(default="", description="失败原因；成功时为空串")
    created_at: str


class KbDocumentPage(BaseModel):
    total: int
    documents: list[KbDocumentItem]


class KbUploadResult(BaseModel):
    """上传受理结果：文档进入后台解析，前端轮询详情等待 ready。"""

    doc_id: int
    status: KbDocStatus
