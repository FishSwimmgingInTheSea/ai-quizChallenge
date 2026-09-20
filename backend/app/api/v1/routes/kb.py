"""知识库接口：文档上传 / 列表 / 详情 / 删除（kb-rag）。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile

from app.api.deps import get_current_user, get_kb_service
from app.api.response import ok
from app.db.orm_models import User
from app.services.kb_service import KbService

router = APIRouter(prefix="/kb", tags=["kb"])


@router.post("/documents")
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="知识库文档：pdf / docx / md / txt"),
    user: User = Depends(get_current_user),
    service: KbService = Depends(get_kb_service),
) -> dict:
    """受理文档上传（登录）：落盘建行后由后台任务解析与向量化，返回 doc_id 与初始状态。"""
    content = file.file.read()
    result = service.create_document(user.id, file.filename or "", content)
    background_tasks.add_task(service.process_document, user.id, result.doc_id)
    return ok(result.model_dump())


@router.get("/documents")
def list_documents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    service: KbService = Depends(get_kb_service),
) -> dict:
    """当前用户的知识库文档列表（created_at 倒序，分页）。"""
    return ok(service.list_documents(user.id, limit, offset).model_dump())


@router.get("/documents/{doc_id}")
def get_document(
    doc_id: int,
    user: User = Depends(get_current_user),
    service: KbService = Depends(get_kb_service),
) -> dict:
    """单文档详情（仅本人可读）。"""
    return ok(service.get_document(user.id, doc_id).model_dump())


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: int,
    user: User = Depends(get_current_user),
    service: KbService = Depends(get_kb_service),
) -> dict:
    """删除文档：向量 + 原始文件 + 记录三者清理（仅本人可删）。"""
    service.delete_document(user.id, doc_id)
    return ok(None)
