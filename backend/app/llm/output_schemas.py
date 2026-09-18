"""LLM 结构化输出 Schema（with_structured_output 的目标）。

与领域模型区分：draft 不含业务 id，由服务层生成 id 后再落地为 Question。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.common import Difficulty, QuestionType


class OptionSchema(BaseModel):
    key: str = Field(description="选项字母 A/B/C/D")
    text: str = Field(description="选项文本")


class QuestionDraft(BaseModel):
    """单题结构化输出。"""

    type: QuestionType = Field(description="题型：single/multiple/judge")
    stem: str = Field(description="题干")
    options: list[OptionSchema] = Field(description="选项列表")
    answer: list[str] = Field(description="正确答案的选项 key 列表")
    explanation: str = Field(description="详细讲解")
    knowledge_point: str = Field(description="知识点标签")
    difficulty: Difficulty = Field(description="难度：easy/medium/hard")


class QuizMetaDraft(BaseModel):
    """题库元信息结构化输出。"""

    title: str = Field(description="题库标题")
    summary: str = Field(description="题库主题摘要")


class ReportDraft(BaseModel):
    """复盘报告结构化输出。"""

    accuracy: int = Field(description="正确率 0~100")
    mastered_points: list[str] = Field(description="已掌握知识点")
    weak_points: list[str] = Field(description="薄弱知识点")
    three_line_summary: list[str] = Field(description="三句知识总结")
    advice: list[str] = Field(description="后续建议")
    share_quote: str = Field(description="分享金句")
