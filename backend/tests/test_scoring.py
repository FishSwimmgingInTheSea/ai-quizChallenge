"""评分与统计纯函数测试。"""

from __future__ import annotations

from app.models.quiz import AnswerRecord, Option, Question
from app.services.scoring_service import compute_score_summary, judge_answer


def _q(qid: str, answer: list[str], kp: str, qtype="single") -> Question:
    return Question(
        id=qid,
        type=qtype,
        stem="题干",
        options=[Option(key=k, text=k) for k in ["A", "B", "C", "D"]],
        answer=answer,
        explanation="讲解",
        knowledge_point=kp,
        difficulty="easy",
    )


def test_judge_answer_set_equality():
    q = _q("q1", ["A", "C"], "kp", qtype="multiple")
    assert judge_answer(q, ["C", "A"]) is True
    assert judge_answer(q, ["A"]) is False
    assert judge_answer(q, []) is False


def test_compute_score_summary_accuracy_and_points():
    questions = [
        _q("q1", ["A"], "概念"),
        _q("q2", ["B"], "边界"),
        _q("q3", ["A", "C"], "场景", qtype="multiple"),
    ]
    records = [
        AnswerRecord(question_id="q1", selected_answers=["A"], is_correct=True),
        AnswerRecord(question_id="q2", selected_answers=["A"], is_correct=False),
        AnswerRecord(question_id="q3", selected_answers=["A", "C"], is_correct=True),
    ]
    summary = compute_score_summary(questions, records)
    assert summary["total"] == 3
    assert summary["correct_count"] == 2
    assert summary["accuracy"] == 67
    assert "概念" in summary["mastered_points"]
    assert "场景" in summary["mastered_points"]
    assert summary["weak_points"] == ["边界"]


def test_compute_score_summary_backend_recompute_overrides_client_flag():
    # 前端谎报 is_correct=True，但后端复算应判为错
    questions = [_q("q1", ["A"], "概念")]
    records = [
        AnswerRecord(question_id="q1", selected_answers=["B"], is_correct=True)
    ]
    summary = compute_score_summary(questions, records)
    assert summary["correct_count"] == 0
    assert summary["accuracy"] == 0


def test_empty_quiz_accuracy_zero():
    assert compute_score_summary([], [])["accuracy"] == 0
