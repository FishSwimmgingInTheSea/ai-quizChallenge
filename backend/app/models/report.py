"""复盘报告领域模型（对齐方案 §10.4）。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.quiz import AnswerRecord, Question


class GenerateReportRequest(BaseModel):
    quiz_id: str
    topic: str
    questions: list[Question] = Field(default_factory=list)
    answer_records: list[AnswerRecord] = Field(default_factory=list)


class Report(BaseModel):
    accuracy: int = Field(ge=0, le=100)
    mastered_points: list[str] = Field(default_factory=list)
    weak_points: list[str] = Field(default_factory=list)
    three_line_summary: list[str] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)
    share_quote: str = ""
