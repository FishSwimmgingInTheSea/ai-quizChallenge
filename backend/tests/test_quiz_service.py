"""出题服务：题型编排、校验、重试、同步/异步生成、联网研究编排测试。"""

from __future__ import annotations

import pytest

from app.core.exceptions import GenerationError
from app.llm.output_schemas import OptionSchema, QuestionDraft
from app.models.quiz import GenerateQuizRequest, TaskState
from app.prompts.quiz_prompt import AUTO_KB_TOPIC, NO_RESEARCH_CONTEXT
from app.services.quiz_service import (
    QuizService,
    is_duplicate_stem,
    plan_question_types,
    resolve_difficulty,
    validate_question_draft,
)
from app.services.research_service import ResearchOutcome
from app.services.image_service import LOGIN_NOTICE, QUOTA_NOTICE, ImagePlan
from app.services.task_store import TaskStore
from tests.conftest import (
    FakeQuizGenerator,
    FakeResearchService,
    FlakyQuizGenerator,
    WrongTypeQuizGenerator,
    make_draft,
    make_research_outcome,
)


# ---------- 题型编排 ----------
def test_plan_question_types_five():
    types = plan_question_types(5)
    assert len(types) == 5
    assert types.count("single") == 3
    assert types.count("multiple") == 1
    assert types.count("judge") == 1


def test_plan_question_types_min():
    assert plan_question_types(0) == ["single"]
    assert plan_question_types(1) == ["single"]
    assert plan_question_types(2) == ["single", "judge"]


def test_resolve_difficulty():
    assert resolve_difficulty("hard", 1) == "hard"
    assert resolve_difficulty("mixed", 1) in ("easy", "medium", "hard")


# ---------- 校验 ----------
def test_validate_rejects_wrong_type():
    draft = make_draft("judge", 1)
    with pytest.raises(GenerationError):
        validate_question_draft(draft, "single")


def test_validate_rejects_answer_out_of_options():
    draft = QuestionDraft(
        type="single",
        stem="题",
        options=[OptionSchema(key="A", text="a"), OptionSchema(key="B", text="b")],
        answer=["C"],
        explanation="讲解",
        knowledge_point="kp",
        difficulty="easy",
    )
    with pytest.raises(GenerationError):
        validate_question_draft(draft, "single")


def test_validate_rejects_single_with_multiple_answers():
    draft = QuestionDraft(
        type="single",
        stem="题",
        options=[OptionSchema(key="A", text="a"), OptionSchema(key="B", text="b")],
        answer=["A", "B"],
        explanation="讲解",
        knowledge_point="kp",
        difficulty="easy",
    )
    with pytest.raises(GenerationError):
        validate_question_draft(draft, "single")


def test_validate_accepts_valid_multiple():
    validate_question_draft(make_draft("multiple", 1), "multiple")


# ---------- 同步生成 ----------
async def test_generate_quiz_sync_produces_full_quiz():
    gen = FakeQuizGenerator()
    service = QuizService(generator=gen, research=FakeResearchService())
    quiz = await service.generate_quiz_sync(
        GenerateQuizRequest(user_input="学习 RAG", question_count=5)
    )
    assert len(quiz.questions) == 5
    assert quiz.quiz_id.startswith("quiz_")
    assert quiz.title
    # 题目 id 递增且唯一
    ids = [q.id for q in quiz.questions]
    assert ids == ["q1", "q2", "q3", "q4", "q5"]
    assert gen.meta_calls == 1
    assert gen.question_calls == 5


# ---------- 重试 ----------
async def test_generation_retries_then_succeeds():
    gen = FlakyQuizGenerator(fail_times=1)
    service = QuizService(
        generator=gen, research=FakeResearchService(), retry_attempts=3
    )
    quiz = await service.generate_quiz_sync(
        GenerateQuizRequest(user_input="学习 RAG", question_count=1)
    )
    assert len(quiz.questions) == 1
    # 1 次失败 + 1 次成功
    assert gen.question_calls == 2


async def test_generation_fails_after_exhausting_retries():
    service = QuizService(
        generator=WrongTypeQuizGenerator(),
        research=FakeResearchService(),
        retry_attempts=2,
    )
    with pytest.raises(GenerationError):
        await service.generate_quiz_sync(
            GenerateQuizRequest(user_input="学习 RAG", question_count=1)
        )


# ---------- 去重硬校验（实测 deepseek-flash 会稳定照抄已有题干） ----------
def test_is_duplicate_stem_detects_copy_and_paraphrase():
    # 归一化后全等：空白与标点差异不影响判定
    assert is_duplicate_stem(
        "微信小程序中，使用分包加载最主要的好处是什么？",
        ["微信小程序中使用分包加载最主要的好处是什么"],
    )
    # 同义改写型重复（实测模型照抄型变体）
    assert is_duplicate_stem(
        "使用分包加载最主要的好处是什么？",
        ["使用分包加载最主要的优点是什么？"],
    )
    # 不同知识点不误杀
    assert not is_duplicate_stem(
        "分包加载的主包体积上限是多少？",
        ["使用分包加载最主要的好处是什么？"],
    )


class DuplicateOnceGenerator(FakeQuizGenerator):
    """第 2 题首次尝试照抄第 1 题（模拟实测的模型照抄行为），之后恢复。"""

    def __init__(self) -> None:
        super().__init__()
        self._dup_done = False

    async def generate_question(self, *args, **kwargs) -> QuestionDraft:  # type: ignore[override]
        self.question_calls += 1
        qtype = args[1] if len(args) > 1 else kwargs["question_type"]
        index = args[3] if len(args) > 3 else kwargs["index"]
        if index == 2 and not self._dup_done:
            self._dup_done = True
            return make_draft(qtype, 1)  # 照抄第 1 题
        return make_draft(qtype, index)


async def test_duplicate_stem_triggers_retry_and_recovers():
    """重复题触发重试，重试产出不重复题，最终题库无重复。"""
    gen = DuplicateOnceGenerator()
    service = QuizService(
        generator=gen, research=FakeResearchService(), retry_attempts=3
    )
    quiz = await service.generate_quiz_sync(
        GenerateQuizRequest(user_input="学习 RAG", question_count=5)
    )
    # 5 题 + 第 2 题的 1 次查重重试
    assert gen.question_calls == 6
    stems = [q.stem for q in quiz.questions]
    assert len(set(stems)) == 5


async def test_duplicate_stem_fallback_accepts_after_retries():
    """重试耗尽仍重复：最后一次免除查重兑底，任务完成优先于完美去重。"""

    class AlwaysDuplicateGenerator(FakeQuizGenerator):
        async def generate_question(self, *args, **kwargs) -> QuestionDraft:  # type: ignore[override]
            self.question_calls += 1
            qtype = args[1] if len(args) > 1 else kwargs["question_type"]
            return make_draft(qtype, 1)  # 永远照抄第 1 题

    gen = AlwaysDuplicateGenerator()
    service = QuizService(
        generator=gen, research=FakeResearchService(), retry_attempts=3
    )
    # count=4 → [single, single, multiple, judge]，前两题同型才能构成照抄重复
    quiz = await service.generate_quiz_sync(
        GenerateQuizRequest(user_input="学习 RAG", question_count=4)
    )
    # 第 1 题 1 次 + 第 2 题 3 次耗尽后兑底接受 + 第 3/4 题各 1 次
    assert len(quiz.questions) == 4
    assert gen.question_calls == 6
    assert quiz.questions[1].stem == quiz.questions[0].stem  # 兑底接受重复
    assert quiz.questions[2].stem != quiz.questions[0].stem


# ---------- 异步任务式生成 ----------
async def test_run_generation_updates_task_state():
    gen = FakeQuizGenerator()
    service = QuizService(generator=gen, research=FakeResearchService())
    store = TaskStore(ttl_seconds=100)
    req = GenerateQuizRequest(user_input="学习 RAG", question_count=5)
    store.create(TaskState(task_id="t1", total=5))

    await service.run_generation("t1", req, store)

    state = store.get("t1")
    assert state.status == "done"
    assert state.generated_count == 5
    assert len(state.questions) == 5
    assert state.title


async def test_run_generation_marks_failed_on_error():
    service = QuizService(
        generator=WrongTypeQuizGenerator(),
        research=FakeResearchService(),
        retry_attempts=1,
    )
    store = TaskStore(ttl_seconds=100)
    req = GenerateQuizRequest(user_input="学习 RAG", question_count=1)
    store.create(TaskState(task_id="t1", total=1))

    await service.run_generation("t1", req, store)

    state = store.get("t1")
    assert state.status == "failed"
    assert state.error


# ---------- 联网研究编排（quiz-web-search-grounding） ----------
async def test_run_generation_research_context_flows_to_generator():
    """研究先于 meta：研究产出作为资料块传入 meta 与全部单题。"""
    outcome = make_research_outcome()
    gen = FakeQuizGenerator()
    research = FakeResearchService(outcome=outcome)
    service = QuizService(generator=gen, research=research)
    store = TaskStore(ttl_seconds=100)
    req = GenerateQuizRequest(user_input="Harness Engineering", question_count=5)
    store.create(TaskState(task_id="t1", total=5))

    await service.run_generation("t1", req, store)

    # 研究恰好执行一次且收到用户原始输入
    assert research.calls == 1
    assert research.inputs[0] == "Harness Engineering"
    # 若 meta 先于 research 执行，此处会收到占位文本而非研究产出
    assert gen.meta_research_contexts[0] == outcome.context_text
    assert all(ctx == outcome.context_text for ctx in gen.question_research_contexts)

    state = store.get("t1")
    assert state.status == "done"
    assert state.research_used is True
    assert state.phase == "generating"


async def test_run_generation_degraded_research_still_completes():
    """研究降级：任务不失败，生成器收到占位文本，research_used 为 false。"""
    gen = FakeQuizGenerator()
    service = QuizService(
        generator=gen,
        research=FakeResearchService(  # 显式降级：无资料
            outcome=ResearchOutcome.degraded_with("mock 降级")
        ),
    )
    store = TaskStore(ttl_seconds=100)
    req = GenerateQuizRequest(user_input="任意主题", question_count=5)
    store.create(TaskState(task_id="t1", total=5))

    await service.run_generation("t1", req, store)

    state = store.get("t1")
    assert state.status == "done"
    assert state.generated_count == 5
    assert state.research_used is False
    assert gen.meta_research_contexts[0] == NO_RESEARCH_CONTEXT
    assert gen.question_research_contexts[0] == NO_RESEARCH_CONTEXT


async def test_run_generation_phase_researching_during_research():
    """研究执行期间任务处于 researching 阶段；结束后回写 research_used。"""
    store = TaskStore(ttl_seconds=100)
    observed: dict = {}

    class ObservingResearch:
        async def research(
            self,
            user_input: str,
            *,
            user_id: int | None = None,
            kb_doc_ids: list[int] | None = None,
        ) -> ResearchOutcome:
            state = store.get("t1")
            observed["status"] = state.status
            observed["phase"] = state.phase
            observed["research_used"] = state.research_used
            return make_research_outcome()

    service = QuizService(generator=FakeQuizGenerator(), research=ObservingResearch())
    req = GenerateQuizRequest(user_input="新术语", question_count=5)
    store.create(TaskState(task_id="t1", total=5))

    await service.run_generation("t1", req, store)

    # 研究期间：status 已是 generating，phase 为 researching，research_used 未知
    assert observed["status"] == "generating"
    assert observed["phase"] == "researching"
    assert observed["research_used"] is None
    # 研究完成后：phase 切换，research_used 回写
    final = store.get("t1")
    assert final.phase == "generating"
    assert final.research_used is True


async def test_generate_quiz_sync_passes_research_context():
    """同步链路同样先研究后出题。"""
    outcome = make_research_outcome()
    gen = FakeQuizGenerator()
    service = QuizService(
        generator=gen, research=FakeResearchService(outcome=outcome)
    )
    quiz = await service.generate_quiz_sync(
        GenerateQuizRequest(user_input="学习 RAG", question_count=5)
    )
    assert len(quiz.questions) == 5
    assert gen.meta_research_contexts[0] == outcome.context_text
    assert gen.question_research_contexts[0] == outcome.context_text


# ---------- 自动出题（空输入 + 知识库：主题兜底替换） ----------
async def test_auto_topic_from_research_replaces_empty_input():
    """空输入：出题 prompt 收到研究推断的主题而非空串。"""
    gen = FakeQuizGenerator()
    research = FakeResearchService(
        outcome=ResearchOutcome(context_text="资料要点", topic="员工手册核心制度")
    )
    service = QuizService(generator=gen, research=research)
    quiz = await service.generate_quiz_sync(
        GenerateQuizRequest(user_input="", kb_doc_ids=[3])
    )
    assert gen.meta_inputs[0] == "员工手册核心制度"
    assert quiz.user_input == "员工手册核心制度"


async def test_auto_topic_fallback_when_research_degraded():
    """空输入 + 研究降级：回退固定主题文案，出题链路不断。"""
    gen = FakeQuizGenerator()
    service = QuizService(generator=gen, research=FakeResearchService())
    quiz = await service.generate_quiz_sync(
        GenerateQuizRequest(user_input="", kb_doc_ids=[3])
    )
    assert gen.meta_inputs[0] == AUTO_KB_TOPIC
    assert quiz.user_input == AUTO_KB_TOPIC
    assert gen.meta_research_contexts[0] == NO_RESEARCH_CONTEXT


async def test_non_empty_input_keeps_user_topic():
    """回归：非空输入仍用用户原主题，研究推断主题不覆盖。"""
    gen = FakeQuizGenerator()
    research = FakeResearchService(
        outcome=ResearchOutcome(context_text="要点", topic="另一个主题")
    )
    service = QuizService(generator=gen, research=research)
    await service.generate_quiz_sync(GenerateQuizRequest(user_input="学习 RAG"))
    assert gen.meta_inputs[0] == "学习 RAG"


# ---------- 出题配图（question-images） ----------
class FakeImageService:
    """配图服务替身：plan 门禁 + 逐题 generate_for_question。"""

    def __init__(
        self,
        *,
        enabled: bool = True,
        notice: str = "",
        fail_ids: set[str] | None = None,
        url_notice: str | None = None,
    ) -> None:
        self._enabled = enabled
        self._notice = notice
        self._fail_ids = set(fail_ids or set())
        self._url_notice = url_notice
        self.calls: list = []

    def plan(self, user_id: int | None) -> ImagePlan:
        return ImagePlan(self._enabled, self._notice)

    async def generate_for_question(self, question, *, user_id):
        self.calls.append(question)
        if question.id in self._fail_ids:
            return None, None
        if self._url_notice:
            return None, self._url_notice
        return f"https://cos.example.com/{question.id}.png", None


async def test_run_generation_backfills_images_when_enabled():
    """勾选配图 + 登录：逐题并发生图，image_url 回填，进入 imaging 阶段。"""
    gen = FakeQuizGenerator()
    img = FakeImageService()
    service = QuizService(
        generator=gen, research=FakeResearchService(), image_service=img
    )
    store = TaskStore(ttl_seconds=100)
    req = GenerateQuizRequest(
        user_input="学习 RAG", question_count=5, generate_images=True
    )
    store.create(TaskState(task_id="t1", total=5))

    await service.run_generation("t1", req, store, user_id=1)

    state = store.get("t1")
    assert state.status == "done"
    assert state.phase == "imaging"
    assert len(img.calls) == 5
    assert all(q.image_url for q in state.questions)
    assert state.questions[0].image_url == "https://cos.example.com/q1.png"
    assert state.image_notice == ""


async def test_run_generation_single_image_failure_only_affects_that_question():
    """单题生图失败仅该题不带图，任务仍 done、其余题正常配图。"""
    gen = FakeQuizGenerator()
    img = FakeImageService(fail_ids={"q2"})
    service = QuizService(
        generator=gen, research=FakeResearchService(), image_service=img
    )
    store = TaskStore(ttl_seconds=100)
    req = GenerateQuizRequest(
        user_input="学习 RAG", question_count=3, generate_images=True
    )
    store.create(TaskState(task_id="t1", total=3))

    await service.run_generation("t1", req, store, user_id=1)

    state = store.get("t1")
    assert state.status == "done"
    assert state.questions[0].image_url
    assert state.questions[1].image_url == ""
    assert state.questions[2].image_url


async def test_run_generation_no_images_when_not_requested():
    """未勾选配图：不触发生图，不进入 imaging 阶段，链路与既有一致。"""
    gen = FakeQuizGenerator()
    img = FakeImageService()
    service = QuizService(
        generator=gen, research=FakeResearchService(), image_service=img
    )
    store = TaskStore(ttl_seconds=100)
    req = GenerateQuizRequest(user_input="学习 RAG", question_count=5)
    store.create(TaskState(task_id="t1", total=5))

    await service.run_generation("t1", req, store, user_id=1)

    state = store.get("t1")
    assert state.status == "done"
    assert img.calls == []
    assert state.phase == "generating"
    assert all(q.image_url == "" for q in state.questions)


async def test_run_generation_anonymous_sets_login_notice():
    """勾选配图但未登录：门禁不通过，不生图，回写登录提示。"""
    gen = FakeQuizGenerator()
    img = FakeImageService(enabled=False, notice=LOGIN_NOTICE)
    service = QuizService(
        generator=gen, research=FakeResearchService(), image_service=img
    )
    store = TaskStore(ttl_seconds=100)
    req = GenerateQuizRequest(
        user_input="学习 RAG", question_count=3, generate_images=True
    )
    store.create(TaskState(task_id="t1", total=3))

    await service.run_generation("t1", req, store, user_id=None)

    state = store.get("t1")
    assert state.status == "done"
    assert img.calls == []
    assert state.image_notice == LOGIN_NOTICE
    assert all(q.image_url == "" for q in state.questions)


async def test_run_generation_quota_notice_recorded():
    """额度用尽：生图返回配额提示，题目不带图，image_notice 记录提示。"""
    gen = FakeQuizGenerator()
    img = FakeImageService(url_notice=QUOTA_NOTICE)
    service = QuizService(
        generator=gen, research=FakeResearchService(), image_service=img
    )
    store = TaskStore(ttl_seconds=100)
    req = GenerateQuizRequest(
        user_input="学习 RAG", question_count=3, generate_images=True
    )
    store.create(TaskState(task_id="t1", total=3))

    await service.run_generation("t1", req, store, user_id=1)

    state = store.get("t1")
    assert state.status == "done"
    assert state.image_notice == QUOTA_NOTICE
    assert all(q.image_url == "" for q in state.questions)


async def test_generate_quiz_sync_backfills_images():
    """同步链路勾选配图：回填每题 image_url。"""
    gen = FakeQuizGenerator()
    img = FakeImageService()
    service = QuizService(
        generator=gen, research=FakeResearchService(), image_service=img
    )
    quiz = await service.generate_quiz_sync(
        GenerateQuizRequest(
            user_input="学习 RAG", question_count=3, generate_images=True
        ),
        user_id=1,
    )
    assert len(img.calls) == 3
    assert all(q.image_url for q in quiz.questions)


async def test_generate_quiz_sync_no_images_when_not_requested():
    """同步链路未勾选配图：不生图。"""
    gen = FakeQuizGenerator()
    img = FakeImageService()
    service = QuizService(
        generator=gen, research=FakeResearchService(), image_service=img
    )
    quiz = await service.generate_quiz_sync(
        GenerateQuizRequest(user_input="学习 RAG", question_count=3), user_id=1
    )
    assert img.calls == []
    assert all(q.image_url == "" for q in quiz.questions)
