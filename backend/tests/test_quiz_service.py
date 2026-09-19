"""出题服务：题型编排、校验、重试、同步/异步生成、联网研究编排测试。"""

from __future__ import annotations

import pytest

from app.core.exceptions import GenerationError
from app.llm.output_schemas import OptionSchema, QuestionDraft
from app.models.quiz import GenerateQuizRequest, TaskState
from app.prompts.quiz_prompt import NO_RESEARCH_CONTEXT
from app.services.quiz_service import (
    QuizService,
    plan_question_types,
    resolve_difficulty,
    validate_question_draft,
)
from app.services.research_service import ResearchOutcome
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
        async def research(self, user_input: str) -> ResearchOutcome:
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
