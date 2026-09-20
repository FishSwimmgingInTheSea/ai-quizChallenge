"""出题应用服务：编排单题循环生成、校验、重试与任务状态更新。

对齐方案 §7.4 可靠性设计与 §9.4.2 后端设计。
"""

from __future__ import annotations

import asyncio
import difflib
import re
from typing import Awaitable, Callable, TypeVar

from app.core.exceptions import GenerationError
from app.core.logging import get_logger
from app.llm.output_schemas import OptionSchema, QuestionDraft, QuizMetaDraft
from app.llm.quiz_chain import LangChainQuizGenerator, QuizGenerator
from app.models.common import Difficulty, QuestionType
from app.models.quiz import GenerateQuizRequest, Option, Question, Quiz, TaskState
from app.prompts.quiz_prompt import AUTO_KB_TOPIC, NO_RESEARCH_CONTEXT
from app.services.research_service import (
    ResearchOutcome,
    ResearchProvider,
    get_research_service,
)
from app.services.image_service import get_image_service
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


# ---------- 去重硬校验（实测 deepseek-flash 会稳定照抄已有题干，纯 Prompt 约束不可靠） ----------
_STEM_PUNCT_RE = re.compile(r"[\s，。？！、；：（）\[\]【】,.?!;:]+")


def _normalize_stem(text: str) -> str:
    """题干归一化：剔除空白与常见标点，仅保留实义字符用于比较。"""
    return _STEM_PUNCT_RE.sub("", text)


def is_duplicate_stem(
    new_stem: str, existing_stems: list[str], threshold: float = 0.8
) -> bool:
    """判断新题干是否与已有题干重复：归一化后全等，或相似度达阈值。"""
    norm_new = _normalize_stem(new_stem)
    if not norm_new:
        return False
    for stem in existing_stems:
        norm_old = _normalize_stem(stem)
        if not norm_old:
            continue
        if norm_new == norm_old:
            return True
        if difflib.SequenceMatcher(None, norm_new, norm_old).ratio() >= threshold:
            return True
    return False


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
    """出题服务。生成器与研究服务通过依赖注入，测试可替换为 mock。"""

    def __init__(
        self,
        generator: QuizGenerator | None = None,
        research: ResearchProvider | None = None,
        *,
        retry_attempts: int = 3,
        image_service=None,
    ) -> None:
        self._generator = generator or LangChainQuizGenerator()
        self._research = research or get_research_service()
        self._retry_attempts = retry_attempts
        # 配图服务（question-images）：惰性——None 时首次用到再取全局单例
        self._image_service = image_service

    def _resolve_image_plan(
        self, req: GenerateQuizRequest, user_id: int | None, store: TaskStore, task_id: str
    ) -> tuple[object | None, bool]:
        """配图门禁：返回 (image_service, 是否尝试配图)。

        未勾选配图 -> (None, False)；勾选但门禁不通过 -> 写入降级提示并
        (svc, False)；门禁通过 -> (svc, True)。
        """
        if not req.generate_images:
            return None, False
        svc = self._image_service or get_image_service()
        plan = svc.plan(user_id)
        if not plan.enabled:
            if plan.notice:
                store.set_image_notice(task_id, plan.notice)
            return svc, False
        return svc, True

    async def _collect_images(
        self, task_id: str, store: TaskStore, pending: list[tuple[int, "asyncio.Future"]]
    ) -> None:
        """统一 await 各题配图任务，回填 image_url 与降级提示。

        单题异常/失败只让该题不带图，不牽连其他题与主流程。
        """
        results = await asyncio.gather(
            *[t for _, t in pending], return_exceptions=True
        )
        for (index, _), res in zip(pending, results):
            if isinstance(res, Exception):
                logger.warning("第 %d 题配图任务异常（降级不带图）：%s", index, res)
                continue
            url, notice = res
            if url:
                store.set_question_image(task_id, index, url)
            if notice:
                store.set_image_notice(task_id, notice)

    async def _run_research(
        self,
        user_input: str,
        *,
        user_id: int | None = None,
        kb_doc_ids: list[int] | None = None,
    ) -> ResearchOutcome:
        """出题前联网研究（quiz-web-search-grounding D1 + kb-rag）。

        选中知识库文档时把 user_id / kb_doc_ids 传给研究服务（Agent 自行
        决定知识库检索与联网搜索的取舍）；ResearchService 内部保证一切失败
        路径均降级返回，不抛异常。
        """
        outcome = await self._research.research(
            user_input, user_id=user_id, kb_doc_ids=kb_doc_ids
        )
        if outcome.degraded:
            logger.info("联网研究降级（%s），回退纯模型出题", outcome.degrade_reason)
        return outcome

    @staticmethod
    def _research_context_of(outcome: ResearchOutcome) -> str:
        """研究产出转为出题资料块；无资料时回退占位文本（D5）。"""
        text = outcome.context_text.strip()
        return text if text else NO_RESEARCH_CONTEXT

    @staticmethod
    def _with_auto_topic(
        req: GenerateQuizRequest, outcome: ResearchOutcome
    ) -> GenerateQuizRequest:
        """自动出题（空输入）：用研究推断的主题替换空 user_input 进入出题 prompt。

        研究降级未产出主题时回退固定文案，出题链路不因空主题断掉。
        """
        if req.user_input.strip():
            return req
        topic = outcome.topic.strip() or AUTO_KB_TOPIC
        return req.model_copy(update={"user_input": topic})

    async def _generate_meta(
        self, req: GenerateQuizRequest, research_context: str
    ) -> QuizMetaDraft:
        return await _with_retry(
            lambda: self._generator.generate_meta(
                req.user_input, req.question_count, req.difficulty, research_context
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
        research_context: str,
    ) -> Question:
        """生成单题：字段校验 + 去重硬校验，重复题触发重试。

        被拒题干会并入禁区传给下一次重试（模型看到更大的禁止清单）；
        最后一次尝试免除查重兑底——主题资料极窄时宁可接受重复，
        也不让任务整体失败（与联网研究降级同一取舍，方案 §7.4）。
        """
        difficulty = resolve_difficulty(req.difficulty, index)
        banned: list[str] = list(existing_stems)
        last_exc: Exception | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                draft = await self._generator.generate_question(
                    req.user_input,
                    qtype,
                    difficulty,
                    index,
                    banned,
                    research_context,
                )
                validate_question_draft(draft, qtype)
                if is_duplicate_stem(draft.stem, banned):
                    if attempt < self._retry_attempts:
                        banned.append(draft.stem)
                        raise GenerationError(
                            f"第 {index} 题与已生成题目重复，需换知识点重出"
                        )
                    logger.warning(
                        "第 %d 题重试 %d 次后仍与已有题目相似，按兑底策略接受",
                        index,
                        self._retry_attempts,
                    )
                return draft_to_question(draft, index)
            except Exception as exc:  # noqa: BLE001 - 需要兑底一切模型侧异常
                last_exc = exc
                logger.warning(
                    "生成第 %d 题 第 %d/%d 次失败：%s",
                    index,
                    attempt,
                    self._retry_attempts,
                    exc,
                )
        raise GenerationError(f"生成第 {index} 题多次失败：{last_exc}")

    async def generate_quiz_sync(
        self, req: GenerateQuizRequest, *, user_id: int | None = None
    ) -> Quiz:
        """同步一次性生成完整题库（调试接口 /sync 用）。"""
        outcome = await self._run_research(
            req.user_input, user_id=user_id, kb_doc_ids=req.kb_doc_ids
        )
        req = self._with_auto_topic(req, outcome)
        research_context = self._research_context_of(outcome)
        types = plan_question_types(req.question_count)
        meta = await self._generate_meta(req, research_context)
        quiz = Quiz(
            quiz_id=new_quiz_id(),
            title=meta.title,
            summary=meta.summary,
            user_input=req.user_input,
            questions=[],
        )
        stems: list[str] = []
        for idx, qtype in enumerate(types, start=1):
            question = await self._generate_one(
                req, qtype, idx, stems, research_context
            )
            quiz.questions.append(question)
            stems.append(question.stem)

        # 配图（question-images）：同步链路直接回填 image_url，门禁不通过则跳过
        if req.generate_images:
            svc = self._image_service or get_image_service()
            if svc.plan(user_id).enabled:
                results = await asyncio.gather(
                    *[
                        svc.generate_for_question(q, user_id=user_id)
                        for q in quiz.questions
                    ],
                    return_exceptions=True,
                )
                for q, res in zip(quiz.questions, results):
                    if isinstance(res, Exception):
                        logger.warning("配图任务异常（降级不带图）：%s", res)
                        continue
                    url, _ = res
                    if url:
                        q.image_url = url
        return quiz

    async def run_generation(
        self,
        task_id: str,
        req: GenerateQuizRequest,
        store: TaskStore,
        user_id: int | None = None,
    ) -> None:
        """后台任务：联网研究 → 元信息 → 逐题生成，实时更新任务状态。

        user_id 由路由层在用户登录时传入：既用于知识库检索（kb-rag），
        也用于配图门禁与配额归属（question-images D9）。
        """
        types = plan_question_types(req.question_count)
        store.set_status(task_id, "generating")
        store.set_phase(task_id, "researching")
        pending_images: list[tuple[int, "asyncio.Future"]] = []
        try:
            outcome = await self._run_research(
                req.user_input, user_id=user_id, kb_doc_ids=req.kb_doc_ids
            )
            req = self._with_auto_topic(req, outcome)
            research_context = self._research_context_of(outcome)
            store.set_research_used(task_id, not outcome.degraded)
            store.set_phase(task_id, "generating")

            meta = await self._generate_meta(req, research_context)
            store.set_meta(task_id, new_quiz_id(), meta.title, meta.summary)

            # 配图门禁（question-images）：勾选且门禁通过才逐题并发生图
            image_svc, image_enabled = self._resolve_image_plan(
                req, user_id, store, task_id
            )

            stems: list[str] = []
            for idx, qtype in enumerate(types, start=1):
                question = await self._generate_one(
                    req, qtype, idx, stems, research_context
                )
                store.append_question(task_id, question)
                stems.append(question.stem)
                if image_enabled:
                    # 题目落库即并发起图，与后续出题重叠以压缩总等待
                    pending_images.append(
                        (
                            idx - 1,
                            asyncio.create_task(
                                image_svc.generate_for_question(
                                    question, user_id=user_id
                                )
                            ),
                        )
                    )
                # 让出事件循环，便于轮询接口读到中间态
                await asyncio.sleep(0)

            if pending_images:
                store.set_phase(task_id, "imaging")
                await self._collect_images(task_id, store, pending_images)

            store.set_status(task_id, "done")
        except Exception as exc:  # noqa: BLE001
            logger.error("任务 %s 生成失败：%s", task_id, exc)
            # 出题失败：取消尚未完成的配图任务，避免孤儿任务告警
            for _, task in pending_images:
                task.cancel()
            store.set_error(task_id, str(exc))


def build_task_state(req: GenerateQuizRequest, task_id: str) -> TaskState:
    return TaskState(
        task_id=task_id,
        status="pending",
        total=len(plan_question_types(req.question_count)),
    )
