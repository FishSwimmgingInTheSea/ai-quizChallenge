"""出题应用服务：编排单题循环生成、校验、重试与任务状态更新。

对齐方案 §7.4 可靠性设计与 §9.4.2 后端设计。
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

from app.core.exceptions import GenerationError
from app.core.logging import get_logger
from app.llm.output_schemas import OptionSchema, QuestionDraft, QuizMetaDraft
from app.llm.quiz_chain import LangChainQuizGenerator, QuizGenerator
from app.models.common import Difficulty, QuestionType
from app.models.quiz import GenerateQuizRequest, Option, Question, Quiz, TaskState
from app.services.task_store import TaskStore
from app.utils.id_generator import new_quiz_id, question_id

logger = get_logger(__name__)

T = TypeVar("T")

JUDGE_KEYS = {"A", "B"}


# ---------- 纯函数：题型编排 ----------
def plan_question_types(count: int) -> list[QuestionType]:
    """按题量规划题型分布（方案 §8.2：单选为主，含多选与判断）。

    - count<=0 归一到 1
    - 5 题 => 3 单选 + 1 多选 + 1 判断
    - 通用规则：至少 1 多选、1 判断（count>=3 时），其余补单选
    """
    if count <= 0:
        count = 1
    if count == 1:
        return ["single"]
    if count == 2:
        return ["single", "judge"]

    judge = 1
    multiple = 1
    single = count - judge - multiple
    # 大题量时多选适当增加
    if count >= 8:
        multiple = 2
        single = count - judge - multiple
    types: list[QuestionType] = (
        ["single"] * single + ["multiple"] * multiple + ["judge"] * judge
    )
    return types


def resolve_difficulty(difficulty_request: str, index: int) -> Difficulty:
    """将请求难度映射到单题难度；mixed 时按序轮换。"""
    if difficulty_request in ("easy", "medium", "hard"):
        return difficulty_request  # type: ignore[return-value]
    cycle: list[Difficulty] = ["easy", "easy", "medium", "medium", "hard"]
    return cycle[(index - 1) % len(cycle)]


# ---------- 校验（方案 §7.4 三级校验） ----------
def validate_question_draft(
    draft: QuestionDraft, expected_type: QuestionType
) -> None:
    """字段完整性 / 语义校验，不合格抛 GenerationError 以触发重试。"""
    if draft is None:
        raise GenerationError("模型返回为空")
    if draft.type != expected_type:
        raise GenerationError(f"题型不符：期望 {expected_type}，实际 {draft.type}")
    if not draft.stem or not draft.stem.strip():
        raise GenerationError("题干为空")
    if not draft.explanation or not draft.explanation.strip():
        raise GenerationError("讲解为空")
    if not draft.answer:
        raise GenerationError("缺少正确答案")

    option_keys = {o.key for o in draft.options}

    if expected_type == "judge":
        if option_keys != JUDGE_KEYS:
            raise GenerationError("判断题选项必须为 A/B")
        if len(draft.answer) != 1 or draft.answer[0] not in JUDGE_KEYS:
            raise GenerationError("判断题答案必须为单个 A 或 B")
        return

    if len(draft.options) < 2:
        raise GenerationError("选项数量不足")
    if len(option_keys) != len(draft.options):
        raise GenerationError("选项 key 存在重复")
    if not set(draft.answer).issubset(option_keys):
        raise GenerationError("答案不在选项范围内")

    if expected_type == "single" and len(draft.answer) != 1:
        raise GenerationError("单选题答案必须恰好 1 个")
    if expected_type == "multiple" and len(draft.answer) < 2:
        raise GenerationError("多选题答案至少 2 个")


def draft_to_question(draft: QuestionDraft, index: int) -> Question:
    return Question(
        id=question_id(index),
        type=draft.type,
        stem=draft.stem.strip(),
        options=[Option(key=o.key, text=o.text) for o in draft.options],
        answer=list(draft.answer),
        explanation=draft.explanation.strip(),
        knowledge_point=(draft.knowledge_point or "综合").strip(),
        difficulty=draft.difficulty,
    )


async def _with_retry(
    factory: Callable[[], Awaitable[T]], attempts: int = 3, label: str = "调用"
) -> T:
    """失败重试（方案 §7.4 第 4 点）。最后一次失败则抛出。"""
    last_exc: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            return await factory()
        except Exception as exc:  # noqa: BLE001 - 需要兜底一切模型侧异常
            last_exc = exc
            logger.warning("%s 第 %d/%d 次失败：%s", label, i, attempts, exc)
    raise GenerationError(f"{label}多次失败：{last_exc}")


class QuizService:
    """出题服务。生成器通过依赖注入，测试可替换为 mock。"""

    def __init__(
        self,
        generator: QuizGenerator | None = None,
        *,
        retry_attempts: int = 3,
    ) -> None:
        self._generator = generator or LangChainQuizGenerator()
        self._retry_attempts = retry_attempts

    async def _generate_meta(
        self, req: GenerateQuizRequest
    ) -> QuizMetaDraft:
        return await _with_retry(
            lambda: self._generator.generate_meta(
                req.user_input, req.question_count, req.difficulty
            ),
            attempts=self._retry_attempts,
            label="生成题库元信息",
        )

    async def _generate_one(
        self,
        req: GenerateQuizRequest,
        qtype: QuestionType,
        index: int,
        existing_stems: list[str],
    ) -> Question:
        difficulty = resolve_difficulty(req.difficulty, index)

        async def _once() -> Question:
            draft = await self._generator.generate_question(
                req.user_input, qtype, difficulty, index, existing_stems
            )
            validate_question_draft(draft, qtype)
            return draft_to_question(draft, index)

        return await _with_retry(
            _once, attempts=self._retry_attempts, label=f"生成第 {index} 题"
        )

    async def generate_quiz_sync(self, req: GenerateQuizRequest) -> Quiz:
        """同步一次性生成完整题库（调试接口 /sync 用）。"""
        types = plan_question_types(req.question_count)
        meta = await self._generate_meta(req)
        quiz = Quiz(
            quiz_id=new_quiz_id(),
            title=meta.title,
            summary=meta.summary,
            user_input=req.user_input,
            questions=[],
        )
        stems: list[str] = []
        for idx, qtype in enumerate(types, start=1):
            question = await self._generate_one(req, qtype, idx, stems)
            quiz.questions.append(question)
            stems.append(question.stem)
        return quiz

    async def run_generation(
        self, task_id: str, req: GenerateQuizRequest, store: TaskStore
    ) -> None:
        """后台任务：逐题生成并实时更新任务状态（异步轮询链路）。"""
        types = plan_question_types(req.question_count)
        store.set_status(task_id, "generating")
        try:
            meta = await self._generate_meta(req)
            store.set_meta(task_id, new_quiz_id(), meta.title, meta.summary)

            stems: list[str] = []
            for idx, qtype in enumerate(types, start=1):
                question = await self._generate_one(req, qtype, idx, stems)
                store.append_question(task_id, question)
                stems.append(question.stem)
                # 让出事件循环，便于轮询接口读到中间态
                await asyncio.sleep(0)

            store.set_status(task_id, "done")
        except Exception as exc:  # noqa: BLE001
            logger.error("任务 %s 生成失败：%s", task_id, exc)
            store.set_error(task_id, str(exc))


def build_task_state(req: GenerateQuizRequest, task_id: str) -> TaskState:
    return TaskState(
        task_id=task_id,
        status="pending",
        total=len(plan_question_types(req.question_count)),
    )
