"""出题服务：题型编排、校验、重试、同步/异步生成测试。"""

from __future__ import annotations

import pytest

from app.core.exceptions import GenerationError
from app.llm.output_schemas import OptionSchema, QuestionDraft
from app.models.quiz import GenerateQuizRequest, TaskState
from app.services.quiz_service import (
    QuizService,
    plan_question_types,
    resolve_difficulty,
    validate_question_draft,
)
from app.services.task_store import TaskStore
from tests.conftest import (
    FakeQuizGenerator,
    FlakyQuizGenerator,
    WrongTypeQuizGenerator,
    make_draft,
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
    service = QuizService(generator=gen)
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
    service = QuizService(generator=gen, retry_attempts=3)
    quiz = await service.generate_quiz_sync(
        GenerateQuizRequest(user_input="学习 RAG", question_count=1)
    )
    assert len(quiz.questions) == 1
    # 1 次失败 + 1 次成功
    assert gen.question_calls == 2


async def test_generation_fails_after_exhausting_retries():
    service = QuizService(generator=WrongTypeQuizGenerator(), retry_attempts=2)
    with pytest.raises(GenerationError):
        await service.generate_quiz_sync(
            GenerateQuizRequest(user_input="学习 RAG", question_count=1)
        )


# ---------- 异步任务式生成 ----------
async def test_run_generation_updates_task_state():
    gen = FakeQuizGenerator()
    service = QuizService(generator=gen)
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
    service = QuizService(generator=WrongTypeQuizGenerator(), retry_attempts=1)
    store = TaskStore(ttl_seconds=100)
    req = GenerateQuizRequest(user_input="学习 RAG", question_count=1)
    store.create(TaskState(task_id="t1", total=1))

    await service.run_generation("t1", req, store)

    state = store.get("t1")
    assert state.status == "failed"
    assert state.error
