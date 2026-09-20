"""题库领域模型（对齐方案 §10）。"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field, model_validator

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
    # 配图永久 URL（question-images）；默认空串保持向后兼容，旧前端忽略即可
    image_url: str = ""


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
    # 空串 = 知识库自动出题：由研究智能体从选中文档推断主题（须选知识库文档）
    user_input: str = ""
    question_count: int = 5
    difficulty: DifficultyRequest = "mixed"
    # 出题引用的知识库文档 id 集合（kb-rag）：非空要求登录且文档属于本人；
    # None / 空 = 不用知识库，链路与原行为完全一致
    kb_doc_ids: list[int] | None = Field(default=None, max_length=10)
    # 是否为每题生成配图（question-images）：默认关闭；仅登录用户生效，
    # 关闭或未登录时出题链路与既有行为逐字一致
    generate_images: bool = False

    @model_validator(mode="after")
    def _check_input_or_kb(self) -> "GenerateQuizRequest":
        """输入与知识库至少占其一：空输入未选文档时无从出题。"""
        if not self.user_input.strip() and not self.kb_doc_ids:
            raise ValueError("user_input 为空时必须选择知识库文档（自动出题）")
        return self


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
    # 配图降级友好提示（question-images）：未登录/额度用尽/依赖不可用时非空；
    # 默认空串保持向后兼容
    image_notice: str = ""
    created_at: float = Field(default_factory=lambda: time.time())

    def to_quiz(self, user_input: str = "") -> Quiz:
        return Quiz(
            quiz_id=self.quiz_id,
            title=self.title,
            summary=self.summary,
            user_input=user_input,
            questions=self.questions,
        )
