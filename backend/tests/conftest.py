"""测试夹具：提供可控的 mock 生成器，全程不触碰真实 DeepSeek。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.llm.output_schemas import (
    OptionSchema,
    QuestionDraft,
    QuizMetaDraft,
    ReportDraft,
)
from app.models.common import Difficulty, QuestionType
from app.services.research_service import ResearchOutcome


# ---------- 用户系统：SQLite 内存库夹具（方案 §4.5） ----------


@pytest.fixture
def db_engine():
    """共享同一个内存连接（StaticPool）的 SQLite 引擎，表结构每夹具新建。"""
    import app.db.orm_models  # noqa: F401  确保模型注册到 Base.metadata
    from app.db.base import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_sessionmaker(db_engine) -> sessionmaker:
    return sessionmaker(bind=db_engine, expire_on_commit=False)


@pytest.fixture
def db_session(db_sessionmaker) -> Session:
    session = db_sessionmaker()
    try:
        yield session
    finally:
        session.close()


def make_draft(qtype: QuestionType, index: int) -> QuestionDraft:
    """按题型构造一个合法的题目草稿。"""
    if qtype == "single":
        return QuestionDraft(
            type="single",
            stem=f"第{index}题：关于该主题，下列说法正确的是？",
            options=[
                OptionSchema(key="A", text="正确的说法"),
                OptionSchema(key="B", text="错误说法一"),
                OptionSchema(key="C", text="错误说法二"),
                OptionSchema(key="D", text="错误说法三"),
            ],
            answer=["A"],
            explanation="因为 A 抓住了核心概念，其余选项存在明显偏差。",
            knowledge_point="核心概念",
            difficulty="easy",
        )
    if qtype == "multiple":
        return QuestionDraft(
            type="multiple",
            stem=f"第{index}题：以下哪些属于典型应用场景？（多选）",
            options=[
                OptionSchema(key="A", text="场景一"),
                OptionSchema(key="B", text="错误项"),
                OptionSchema(key="C", text="场景二"),
                OptionSchema(key="D", text="无关项"),
            ],
            answer=["A", "C"],
            explanation="A 和 C 都是真实落地场景，B、D 与主题无关。",
            knowledge_point="应用场景",
            difficulty="medium",
        )
    return QuestionDraft(
        type="judge",
        stem=f"第{index}题：这个说法是否正确？",
        options=[
            OptionSchema(key="A", text="正确"),
            OptionSchema(key="B", text="错误"),
        ],
        answer=["B"],
        explanation="该说法以偏概全，因此判为错误。",
        knowledge_point="边界辨析",
        difficulty="easy",
    )


class FakeQuizGenerator:
    """始终返回合法草稿的生成器（research_context 仅记录供断言）。"""

    def __init__(self) -> None:
        self.meta_calls = 0
        self.question_calls = 0
        self.meta_research_contexts: list[str] = []
        self.question_research_contexts: list[str] = []

    async def generate_meta(
        self, user_input: str, question_count: int, difficulty: str, research_context: str
    ) -> QuizMetaDraft:
        self.meta_calls += 1
        self.meta_research_contexts.append(research_context)
        return QuizMetaDraft(title=f"{user_input[:8]} 闯关", summary="围绕该主题的闯关题库")

    async def generate_question(
        self,
        user_input: str,
        question_type: QuestionType,
        difficulty: Difficulty,
        index: int,
        existing_stems: list[str],
        research_context: str,
    ) -> QuestionDraft:
        self.question_calls += 1
        self.question_research_contexts.append(research_context)
        return make_draft(question_type, index)


class FlakyQuizGenerator(FakeQuizGenerator):
    """前 N 次生成题目抛错，用于测试重试。"""

    def __init__(self, fail_times: int = 1) -> None:
        super().__init__()
        self._fail_times = fail_times

    async def generate_question(self, *args, **kwargs) -> QuestionDraft:  # type: ignore[override]
        self.question_calls += 1
        if self.question_calls <= self._fail_times:
            raise RuntimeError("模拟模型超时")
        # 减去已失败的次数不影响返回内容
        qtype = args[1] if len(args) > 1 else kwargs["question_type"]
        index = args[3] if len(args) > 3 else kwargs["index"]
        return make_draft(qtype, index)


class WrongTypeQuizGenerator(FakeQuizGenerator):
    """总是返回错误题型，用于测试校验永远失败 -> GenerationError。"""

    async def generate_question(self, *args, **kwargs) -> QuestionDraft:  # type: ignore[override]
        self.question_calls += 1
        # 期望 single 时永远返回 judge
        return make_draft("judge", 1)


class FakeReportGenerator:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(
        self, topic: str, quiz_json: str, answer_records: str, score_summary: str
    ) -> ReportDraft:
        self.calls += 1
        return ReportDraft(
            accuracy=0,  # 故意给错，服务层应以后端复算覆盖
            mastered_points=["核心概念"],
            weak_points=["边界辨析"],
            three_line_summary=["总结一", "总结二", "总结三"],
            advice=["多复习薄弱点"],
            share_quote="把知识做成关卡，记忆会更深。",
        )


class FakeResearchService:
    """可编程研究服务 mock（默认降级，与未配置 key 行为一致）。"""

    def __init__(self, outcome: ResearchOutcome | None = None) -> None:
        self.calls = 0
        self.inputs: list[str] = []
        self._outcome = outcome or ResearchOutcome.degraded_with("mock 默认降级")

    async def research(self, user_input: str) -> ResearchOutcome:
        self.calls += 1
        self.inputs.append(user_input)
        return self._outcome


def make_research_outcome(context_text: str = "") -> ResearchOutcome:
    """构造一个未降级的研究产出（context_text 默认给一段典型资料块）。"""
    from app.llm.output_schemas import ResearchSource

    return ResearchOutcome(
        context_text=context_text
        or "【主题领域判定】\n属于 AI 编码智能体领域的测试工程概念\n\n【资料要点】\n要点一；要点二",
        sources=[ResearchSource(title="文档 A", url="https://a.com")],
    )


@pytest.fixture
def fake_quiz_generator() -> FakeQuizGenerator:
    return FakeQuizGenerator()


@pytest.fixture
def fake_report_generator() -> FakeReportGenerator:
    return FakeReportGenerator()


@pytest.fixture
def fake_research() -> FakeResearchService:
    return FakeResearchService()
