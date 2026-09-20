"""出题接口：异步任务式（提交 + 轮询）+ 同步调试接口。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.api.deps import (
    get_current_user,
    get_kb_service,
    get_optional_user,
    get_quiz_service,
    get_record_service,
    get_store,
)
from app.api.response import ok
from app.core.exceptions import (
    ContentSafetyError,
    TaskNotFoundError,
    UnauthorizedError,
)
from app.db.orm_models import User
from app.models.quiz import GenerateQuizRequest
from app.models.user import RecordSubmitRequest
from app.services.kb_service import KbService
from app.services.quiz_service import QuizService, build_task_state
from app.services.record_service import RecordService
from app.services.task_store import TaskStore
from app.utils.content_filter import contains_sensitive
from app.utils.id_generator import new_task_id
from app.utils.text_cleaner import validate_length

router = APIRouter(prefix="/quiz", tags=["quiz"])


def _preprocess(req: GenerateQuizRequest) -> GenerateQuizRequest:
    """清洗 + 长度校验 + 敏感词预检，返回清洗后的请求副本。

    空输入（知识库自动出题）跳过长度校验，长度下限仅约束用户手写主题。
    """
    cleaned = validate_length(req.user_input) if req.user_input.strip() else ""
    if contains_sensitive(cleaned):
        raise ContentSafetyError()
    return req.model_copy(update={"user_input": cleaned})


def _validate_kb_selection(
    req: GenerateQuizRequest, user: User | None, kb: KbService
) -> int | None:
    """知识库选择校验（kb-rag）：非空时要求登录且文档属于本人且已就绪。

    返回出题可用的 user_id（未选知识库时为 None，链路与原行为一致）。
    """
    if not req.kb_doc_ids:
        return None
    if user is None:
        raise UnauthorizedError()
    kb.get_ready_doc_ids(user.id, req.kb_doc_ids)
    return user.id


@router.post("/generate")
async def generate(
    req: GenerateQuizRequest,
    background_tasks: BackgroundTasks,
    service: QuizService = Depends(get_quiz_service),
    store: TaskStore = Depends(get_store),
    user: User | None = Depends(get_optional_user),
    kb: KbService = Depends(get_kb_service),
) -> dict:
    """提交出题任务，立即返回 task_id（不等待生成完成）。"""
    clean_req = _preprocess(req)
    user_id = _validate_kb_selection(clean_req, user, kb)
    task_id = new_task_id()
    state = build_task_state(clean_req, task_id)
    store.create(state)
    background_tasks.add_task(
        service.run_generation, task_id, clean_req, store, user_id=user_id
    )
    return ok({"task_id": task_id, "status": "pending"})


@router.get("/task/{task_id}")
async def get_task(
    task_id: str,
    store: TaskStore = Depends(get_store),
) -> dict:
    """轮询出题进度。"""
    state = store.get(task_id)
    if state is None:
        raise TaskNotFoundError()
    return ok(state.model_dump())


@router.post("/generate/sync")
async def generate_sync(
    req: GenerateQuizRequest,
    service: QuizService = Depends(get_quiz_service),
    user: User | None = Depends(get_optional_user),
    kb: KbService = Depends(get_kb_service),
) -> dict:
    """同步一次性返回完整题库（仅用于后端联调/压测，方案 §9.1 兼容说明）。"""
    clean_req = _preprocess(req)
    user_id = _validate_kb_selection(clean_req, user, kb)
    quiz = await service.generate_quiz_sync(clean_req, user_id=user_id)
    return ok(quiz.model_dump())


@router.post("/records")
def submit_record(
    req: RecordSubmitRequest,
    user: User = Depends(get_current_user),
    service: RecordService = Depends(get_record_service),
) -> dict:
    """通关结算：服务端复算 + 事务写记录 + 原子加 XP，幂等重放不重复加（方案 §7）。"""
    return ok(service.submit(user.id, req).model_dump())


@router.get("/records")
def list_records(
    limit: int = Query(default=10, ge=1, le=50, description="每页数量，最大 50"),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    service: RecordService = Depends(get_record_service),
) -> dict:
    """历史闯关记录列表，created_at 倒序（方案 §8.1）。"""
    return ok(service.list_records(user.id, limit, offset).model_dump())


@router.get("/records/{record_id}")
def get_record_detail(
    record_id: int,
    user: User = Depends(get_current_user),
    service: RecordService = Depends(get_record_service),
) -> dict:
    """单局记录详情：汇总 + 逐题明细 + 复盘报告（仅本人可读，方案 §12.3）。"""
    return ok(service.get_record_detail(user.id, record_id).model_dump())
