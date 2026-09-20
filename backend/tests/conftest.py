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


# 每题考查不同维度（模拟真实出题多样性，也避免 mock 题干彼此仅差序号、
# 归一化相似度过高而误触发出题服务的查重硬校验）
_SINGLE_STEMS = (
    "下列关于该主题核心概念的表述，哪一项是准确的？",
    "该主题落地实践中，最常见的一个认知误区是什么？",
    "下列哪一项不属于该主题的典型应用场景？",
    "关于该主题的底层工作原理，哪个描述最贴近事实？",
    "以下哪种做法更符合该主题的最佳实践？",
    "该主题与其最易混淆的相近概念，本质区别在于什么？",
)
_MULTIPLE_STEMS = (
    "以下哪些属于该主题的典型应用场景？（多选）",
    "下列哪些做法有助于正确运用该主题的知识？（多选）",
)


def make_draft(qtype: QuestionType, index: int) -> QuestionDraft:
    """按题型构造一个合法的题目草稿。"""
    if qtype == "single":
        return QuestionDraft(
            type="single",
            stem=_SINGLE_STEMS[(index - 1) % len(_SINGLE_STEMS)],
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
            stem=_MULTIPLE_STEMS[(index - 1) % len(_MULTIPLE_STEMS)],
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
        stem="这个说法是否符合该主题的客观事实？",
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
        self.meta_inputs: list[str] = []
        self.meta_research_contexts: list[str] = []
        self.question_research_contexts: list[str] = []

    async def generate_meta(
        self, user_input: str, question_count: int, difficulty: str, research_context: str
    ) -> QuizMetaDraft:
        self.meta_calls += 1
        self.meta_inputs.append(user_input)
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
        self.call_kwargs: list[dict] = []
        self._outcome = outcome or ResearchOutcome.degraded_with("mock 默认降级")

    async def research(
        self,
        user_input: str,
        *,
        user_id: int | None = None,
        kb_doc_ids: list[int] | None = None,
    ) -> ResearchOutcome:
        self.calls += 1
        self.inputs.append(user_input)
        self.call_kwargs.append({"user_id": user_id, "kb_doc_ids": kb_doc_ids})
        return self._outcome


class FakeKbStore:
    """向量库占位 mock：接口路由层的元数据校验不触达真实 Chroma。"""

    def __init__(self, sample_docs: list | None = None) -> None:
        self._sample_docs = sample_docs or []
        self.sample_calls: list[tuple] = []

    def add_chunks(self, *args, **kwargs) -> None: ...

    def search(self, *args, **kwargs) -> list:
        return []

    def sample(self, user_id: int, doc_ids: list, *, per_doc: int = 2) -> list:
        self.sample_calls.append((user_id, tuple(doc_ids), per_doc))
        return list(self._sample_docs)

    def delete_document(self, *args, **kwargs) -> None: ...


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
