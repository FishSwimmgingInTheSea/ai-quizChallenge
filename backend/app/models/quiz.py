"""题库领域模型（对齐方案 §10）。"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field

from app.models.common import Difficulty, DifficultyRequest, QuestionType, TaskStatus


class Option(BaseModel):
    key: str = Field(description="选项字母，如 A/B/C/D")
    text: str = Field(description="选项内容")


class Question(BaseModel):
    id: str
    type: QuestionType
    stem: str
    options: list[Option]
    answer: list[str] = Field(description="正确答案的选项 key 列表")
    explanation: str
    knowledge_point: str
    difficulty: Difficulty


class Quiz(BaseModel):
    quiz_id: str
    title: str
    summary: str
    source_type: str = "text"
    user_input: str
    questions: list[Question] = Field(default_factory=list)


class AnswerRecord(BaseModel):
    question_id: str
    selected_answers: list[str] = Field(default_factory=list)
    is_correct: bool
    duration_ms: int = 0


# ---------- 请求 / 响应 ----------


class GenerateQuizRequest(BaseModel):
    user_input: str
    question_count: int = 5
    difficulty: DifficultyRequest = "mixed"


class GenerateTaskResponse(BaseModel):
    task_id: str
    status: TaskStatus


class TaskState(BaseModel):
    task_id: str
    status: TaskStatus = "pending"
    # 生成阶段（quiz-web-search-grounding D7）：researching / generating；空串保持旧语义
    phase: str = ""
    # 是否实际用上联网研究资料：null = 研究中/未知
    research_used: bool | None = None
    generated_count: int = 0
    total: int = 5
    quiz_id: str = ""
    title: str = ""
    summary: str = ""
    questions: list[Question] = Field(default_factory=list)
    error: str | None = None
    created_at: float = Field(default_factory=lambda: time.time())

    def to_quiz(self, user_input: str = "") -> Quiz:
        return Quiz(
            quiz_id=self.quiz_id,
            title=self.title,
            summary=self.summary,
            user_input=user_input,
            questions=self.questions,
        )
