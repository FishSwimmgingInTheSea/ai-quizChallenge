"""出题接口：异步任务式（提交 + 轮询）+ 同步调试接口。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.deps import get_quiz_service, get_store
from app.api.response import ok
from app.core.exceptions import ContentSafetyError, TaskNotFoundError
from app.models.quiz import GenerateQuizRequest
from app.services.quiz_service import QuizService, build_task_state
from app.services.task_store import TaskStore
from app.utils.content_filter import contains_sensitive
from app.utils.id_generator import new_task_id
from app.utils.text_cleaner import validate_length

router = APIRouter(prefix="/quiz", tags=["quiz"])


def _preprocess(req: GenerateQuizRequest) -> GenerateQuizRequest:
    """清洗 + 长度校验 + 敏感词预检，返回清洗后的请求副本。"""
    cleaned = validate_length(req.user_input)
    if contains_sensitive(cleaned):
        raise ContentSafetyError()
    return req.model_copy(update={"user_input": cleaned})


@router.post("/generate")
async def generate(
    req: GenerateQuizRequest,
    background_tasks: BackgroundTasks,
    service: QuizService = Depends(get_quiz_service),
    store: TaskStore = Depends(get_store),
) -> dict:
    """提交出题任务，立即返回 task_id（不等待生成完成）。"""
    clean_req = _preprocess(req)
    task_id = new_task_id()
    state = build_task_state(clean_req, task_id)
    store.create(state)
    background_tasks.add_task(service.run_generation, task_id, clean_req, store)
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
) -> dict:
    """同步一次性返回完整题库（仅用于后端联调/压测，方案 §9.1 兼容说明）。"""
    clean_req = _preprocess(req)
    quiz = await service.generate_quiz_sync(clean_req)
    return ok(quiz.model_dump())
