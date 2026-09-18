"""领域模型与请求默认值测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.quiz import GenerateQuizRequest, Option, Question, Quiz, TaskState
from app.models.report import Report


def test_generate_quiz_request_defaults():
    req = GenerateQuizRequest(user_input="学习 RAG")
    assert req.question_count == 5
    assert req.difficulty == "mixed"


def test_question_requires_valid_type():
    with pytest.raises(ValidationError):
        Question(
            id="q1",
            type="foo",  # type: ignore[arg-type]
            stem="题干",
            options=[Option(key="A", text="a")],
            answer=["A"],
            explanation="讲解",
            knowledge_point="kp",
            difficulty="easy",
        )


def test_report_accuracy_bounds():
    with pytest.raises(ValidationError):
        Report(accuracy=120)
    ok = Report(accuracy=80)
    assert ok.accuracy == 80


def test_task_state_to_quiz():
    state = TaskState(
        task_id="task_1",
        status="done",
        quiz_id="quiz_1",
        title="标题",
        summary="摘要",
        total=1,
        questions=[
            Question(
                id="q1",
                type="single",
                stem="题",
                options=[Option(key="A", text="a"), Option(key="B", text="b")],
                answer=["A"],
                explanation="讲解",
                knowledge_point="kp",
                difficulty="easy",
            )
        ],
    )
    quiz: Quiz = state.to_quiz(user_input="原始输入")
    assert quiz.quiz_id == "quiz_1"
    assert quiz.user_input == "原始输入"
    assert len(quiz.questions) == 1
