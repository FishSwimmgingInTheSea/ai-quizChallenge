"""报告服务测试。"""

from __future__ import annotations

from app.models.quiz import AnswerRecord, Option, Question
from app.models.report import GenerateReportRequest
from app.services.report_service import ReportService
from tests.conftest import FakeReportGenerator


def _q(qid: str, answer: list[str], kp: str) -> Question:
    return Question(
        id=qid,
        type="single",
        stem="题干",
        options=[Option(key="A", text="a"), Option(key="B", text="b")],
        answer=answer,
        explanation="讲解",
        knowledge_point=kp,
        difficulty="easy",
    )


async def test_report_uses_backend_recomputed_accuracy():
    gen = FakeReportGenerator()
    service = ReportService(generator=gen)
    req = GenerateReportRequest(
        quiz_id="quiz_1",
        topic="RAG 入门",
        questions=[_q("q1", ["A"], "概念"), _q("q2", ["B"], "边界")],
        answer_records=[
            AnswerRecord(question_id="q1", selected_answers=["A"], is_correct=True),
            AnswerRecord(question_id="q2", selected_answers=["A"], is_correct=False),
        ],
    )
    report = await service.generate(req)
    # FakeReportGenerator 返回 accuracy=0，但后端复算应为 50
    assert report.accuracy == 50
    assert len(report.three_line_summary) == 3
    assert report.share_quote
    assert gen.calls == 1
