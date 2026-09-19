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


class ResearchSource(BaseModel):
    """研究资料来源（quiz-web-search-grounding D3）。"""

    title: str = Field(description="来源页面标题")
    url: str = Field(description="来源页面 URL")


class ResearchSummary(BaseModel):
    """研究智能体的结构化总结（create_agent 的 response_format 目标）。"""

    topic_domain: str = Field(
        description="用户主题所属领域的判定与术语含义（领域消歧依据）"
    )
    context_digest: str = Field(
        description="供出题引用的资料要点汇编（核心概念、关键事实、时效信息）"
    )
    sources: list[ResearchSource] = Field(description="资料来源列表")


class ReportDraft(BaseModel):
    """复盘报告结构化输出。"""

    accuracy: int = Field(description="正确率 0~100")
    mastered_points: list[str] = Field(description="已掌握知识点")
    weak_points: list[str] = Field(description="薄弱知识点")
    three_line_summary: list[str] = Field(description="三句知识总结")
    advice: list[str] = Field(description="后续建议")
    share_quote: str = Field(description="分享金句")
