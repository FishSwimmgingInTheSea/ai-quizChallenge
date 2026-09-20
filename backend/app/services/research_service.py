"""联网研究服务（quiz-web-search-grounding D1/D3/D4 + kb-rag 扩展）。

出题前由研究智能体（create_agent + 工具集）自主检索与抓取资料，产出
结构化 ResearchSummary 并拼接为出题可用的 research_context。任何失败
路径（开关关闭 / 未配置 key / 超时 / 异常 / 无资料）均静默降级为纯模型
出题，任务不失败；研究产出带进程内 TTL 缓存（降级结果不缓存，避免一次
网络抖动导致后续请求长时间无资料）。

kb-rag 扩展（Agentic RAG）：用户出题时选中知识库文档则 agent 额外携带
kb_search 工具，由模型自主决定知识库检索与联网搜索的取舍；缓存 key
加 用户/文档集合 维度（知识库内容因人而异，跨用户不可共享）。知识库
不可用（未配 key / 开关关闭 / 匿名请求）时静默忽略选择，退回纯联网。
自动出题模式：空输入 + 知识库可用时预取文档概览注入用户消息，agent
自推主题（topic 随产出返回供出题 prompt 使用）；agent 失败则概览原文
直接作出题资料降级兜底。
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from langchain_core.tools import BaseTool

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.langchain_factory import get_research_model
from app.llm.output_schemas import ResearchSource, ResearchSummary
from app.llm.research_tools import (
    _clip,
    build_kb_search_tool,
    build_research_tools,
)
from app.services.kb_store import get_kb_store

logger = get_logger(__name__)


RESEARCH_SYSTEM_PROMPT = """你是「智趣 AI 闯关学习」小程序的联网研究助手。用户即将基于一个学习主题生成答题闯关题目，而你的职责是在出题前完成资料检索，产出结构化研究总结供出题环节引用，避免大模型因训练数据时效限制而张冠李戴。

工作流程：
1. 检查用户输入是否包含网页链接（http/https URL）：有则优先调用 web_extract 抓取整页正文，页面链接是核心资料；
2. 对新术语、跨领域同名词（同一名字可能对应多个领域的概念），必须先联网搜索确认主题所属领域与术语的准确含义，再深入检索；
3. 自适应选择工具参数：复杂、冷门或新兴主题用 search_depth="advanced" 加 include_full_content=True；简单常见主题默认摘要即可；中文主题建议 country="china"；结果条数与时间范围按需调整；
4. 若首轮检索资料不足，可更换关键词或调整参数补充检索；
5. 资料足够后立即收尾，输出结构化总结（ResearchSummary）。

原则与护栏：
- 工具与模型调用次数有限，够用即收尾，不做重复检索；
- 严禁编造资料中不存在的内容，资料不足以覆盖的主题范围如实说明；
- 总结使用简体中文（专业术语保留英文原文），context_digest 聚焦可支撑出题的核心概念、关键事实与时效信息。"""

# 选中知识库文档时追加的提示词段：私有资料优先，联网作补充
_KB_ADDENDUM = """

私有知识库优先原则（本次用户已选定知识库文档，已提供 kb_search 工具）：
- 用户上传的文档是本次学习的核心资料，出题依据应优先来自 kb_search 检索到的原文片段；
- 私有领域知识（企业制度、内部培训、指定教材/题库）联网通常搜不到，先用 kb_search 再考虑 web_search；
- 知识库片段未覆盖的部分（公开常识、术语背景、时效信息）可用 web_search 补充；
- context_digest 需明确标注哪些要点摘自用户私有知识库。"""

# 自动出题模式（空输入 + 选中知识库）：用户消息改为「文档概览 + 自推主题」指令
_AUTO_MODE_HEAD = (
    "用户未指定学习主题，要求基于其选定的知识库文档自动出题。"
    "系统已预取文档原文概览如下：\n"
)
_AUTO_MODE_TAIL = (
    "\n请先从概览推断文档的核心主题与关键知识点（topic_domain 写明推断出的"
    "学习主题），再自行拟定关键词用 kb_search 深入检索（必要时 web_search 补充），"
    "最后输出研究总结。"
)

# 自动出题概览取样：每文档 chunk 数（纯元数据读取，代价低）
_AUTO_SAMPLE_PER_DOC = 2


def system_prompt_for(with_kb: bool) -> str:
    """研究系统提示词：选了知识库时追加 kb_search 使用指引（原有内容不变）。"""
    return RESEARCH_SYSTEM_PROMPT + _KB_ADDENDUM if with_kb else RESEARCH_SYSTEM_PROMPT


class ResearchProvider(Protocol):
    """联网研究提供方协议（预留博查 / Firecrawl 等替换扩展点）。"""

    async def research(
        self,
        user_input: str,
        *,
        user_id: int | None = None,
        kb_doc_ids: list[int] | None = None,
    ) -> "ResearchOutcome": ...


@dataclass
class ResearchOutcome:
    """研究产出（服务层对象，供出题链路消费）。"""

    context_text: str = ""
    sources: list[ResearchSource] = field(default_factory=list)
    degraded: bool = False
    degrade_reason: str = ""
    # 研究智能体判定的学习主题（自动出题模式空输入时供出题 prompt 兜底）
    topic: str = ""

    @classmethod
    def degraded_with(cls, reason: str) -> "ResearchOutcome":
        return cls(context_text="", sources=[], degraded=True, degrade_reason=reason)


def _build_research_agent(
    *, user_id: int | None = None, kb_doc_ids: list[int] | None = None
) -> Any:
    """默认研究智能体：create_agent + 工具集 + 结构化收尾 + 双限次护栏（D1）。

    工具集按数据源可用性组装：联网双工具（Tavily key 已配）+ kb_search
    （用户选了知识库文档）；user_id / kb_doc_ids 由服务层判定可用后传入。
    """
    settings = get_settings()
    tools: list[BaseTool] = []
    if settings.tavily_api_key:
        tools.extend(build_research_tools(settings))
    with_kb = user_id is not None and bool(kb_doc_ids)
    if with_kb:
        tools.append(
            build_kb_search_tool(
                settings,
                user_id=user_id,
                doc_ids=list(kb_doc_ids),
                kb_store=get_kb_store(),
            )
        )
    return create_agent(
        model=get_research_model(),
        tools=tools,
        response_format=ResearchSummary,
        system_prompt=system_prompt_for(with_kb),
        middleware=[
            ToolCallLimitMiddleware(run_limit=settings.research_max_tool_calls),
            ModelCallLimitMiddleware(run_limit=settings.research_max_model_calls),
        ],
    )


class ResearchService:
    """联网研究服务：编排研究智能体、总超时与产出缓存。

    agent_factory 可注入（测试 mock 智能体，按次接收 user_id / kb_doc_ids
    kwargs）；默认工厂组装 create_agent 官方路径。与 QuizGenerator 同构
    的注入模式。
    """

    def __init__(
        self,
        agent_factory: Callable[..., Any] | None = None,
        *,
        settings: Settings | None = None,
        kb_store: Any | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._agent_factory = agent_factory or _build_research_agent
        # 可注入（测试 mock）；自动出题概览取样用，懒加载全局单例
        self._kb_store = kb_store
        self._cache: dict[str, tuple[ResearchOutcome, float]] = {}
        self._lock = threading.Lock()

    async def research(
        self,
        user_input: str,
        *,
        user_id: int | None = None,
        kb_doc_ids: list[int] | None = None,
    ) -> ResearchOutcome:
        """对用户输入执行联网研究；一切失败路径均降级，绝不抛异常。

        选中知识库文档（user_id + kb_doc_ids 且配置可用）时 agent 额外携带
        kb_search 工具；知识库不可用则静默忽略选择退回纯联网（降级策略）。
        空输入 + 知识库可用 = 自动出题模式：预取文档概览注入用户消息，由
        agent 自推主题；概览为空则降级。
        """
        settings = self._settings
        if not settings.research_enabled:
            return ResearchOutcome.degraded_with("研究总开关关闭（RESEARCH_ENABLED=false）")

        # 知识库可用性判定：无效选择静默忽略（联网/纯模型出题继续）
        kb_requested = bool(kb_doc_ids) and user_id is not None
        kb_usable = (
            kb_requested
            and settings.kb_enabled
            and bool(settings.dashscope_api_key)
        )
        if kb_requested and not kb_usable:
            logger.warning(
                "知识库不可用，已忽略本次文档选择（user=%s, doc_ids=%s）",
                user_id,
                kb_doc_ids,
            )
        effective_user_id = user_id if kb_usable else None
        effective_kb_doc_ids = list(kb_doc_ids) if kb_usable else None

        if not settings.tavily_api_key and effective_kb_doc_ids is None:
            return ResearchOutcome.degraded_with("未配置 TAVILY_API_KEY，跳过联网研究")

        # 自动出题模式：空输入时把文档概览拼进用户消息，agent 据此自推主题
        overview = ""
        agent_input = user_input
        if not user_input.strip() and effective_kb_doc_ids is not None:
            overview = self._kb_overview(effective_user_id, effective_kb_doc_ids)
            if not overview:
                return ResearchOutcome.degraded_with("知识库文档概览为空，无法自动推断主题")
            agent_input = _AUTO_MODE_HEAD + overview + _AUTO_MODE_TAIL

        key = self._cache_key(user_input, effective_user_id, effective_kb_doc_ids)
        cached = self._cache_get(key)
        if cached is not None:
            logger.info("研究缓存命中（key=%s…）", key[:10])
            return cached

        try:
            result = await asyncio.wait_for(
                self._agent_factory(
                    user_id=effective_user_id, kb_doc_ids=effective_kb_doc_ids
                ).ainvoke({"messages": [("user", agent_input)]}),
                timeout=settings.research_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "研究超时（上限 %ss）：%s", settings.research_timeout, user_input[:50]
            )
            return self._auto_fallback_or_degraded(
                overview, f"研究超时（>{settings.research_timeout}s）"
            )
        except Exception as exc:  # noqa: BLE001 - 一切研究侧异常均静默降级
            logger.warning("研究失败：%s", exc)
            return self._auto_fallback_or_degraded(overview, f"研究异常：{exc}")

        summary = (
            result.get("structured_response") if isinstance(result, dict) else None
        )
        if not isinstance(summary, ResearchSummary) or not (
            summary.context_digest or ""
        ).strip():
            return self._auto_fallback_or_degraded(overview, "研究未产出有效资料")

        outcome = self._to_outcome(summary)
        self._cache_put(key, outcome)
        logger.info(
            "研究完成：来源 %d 条，资料 %d 字符",
            len(outcome.sources),
            len(outcome.context_text),
        )
        return outcome

    # ---------- 自动出题（空输入 + 知识库） ----------

    def _kb_overview(self, user_id: int, doc_ids: list[int]) -> str:
        """预取选中文档的原文概览（每文档若干 chunks，纯元数据读取）。"""
        store = self._kb_store or get_kb_store()
        try:
            docs = store.sample(user_id, doc_ids, per_doc=_AUTO_SAMPLE_PER_DOC)
        except Exception as exc:  # noqa: BLE001 - 取样失败走降级，不影响主链路
            logger.warning("自动出题概览取样失败（user=%s）：%s", user_id, exc)
            return ""
        sections = []
        for i, doc in enumerate(docs, start=1):
            meta = doc.metadata or {}
            filename = meta.get("filename") or "（未知文档）"
            sections.append(
                f"【概览 {i}】来源：{filename}\n"
                f"{_clip(doc.page_content, self._settings.research_per_source_max_chars)}"
            )
        if not sections:
            return ""
        return _clip(
            "\n\n".join(sections), self._settings.research_tool_output_max_chars
        )

    @staticmethod
    def _auto_fallback_or_degraded(overview: str, reason: str) -> ResearchOutcome:
        """自动出题模式下 agent 失败：概览原文直接作出题资料，承诺不落空。"""
        if overview:
            return ResearchOutcome(
                context_text=overview,
                degraded=True,
                degrade_reason=f"{reason}，回退文档概览出题",
            )
        return ResearchOutcome.degraded_with(reason)

    # ---------- 产出拼接（D3） ----------

    def _to_outcome(self, summary: ResearchSummary) -> ResearchOutcome:
        parts: list[str] = []
        if (summary.topic_domain or "").strip():
            parts.append(f"【主题领域判定】\n{summary.topic_domain.strip()}")
        if (summary.context_digest or "").strip():
            parts.append(f"【资料要点】\n{summary.context_digest.strip()}")
        sources = [s for s in summary.sources if (s.url or "").strip()]
        if sources:
            lines = "\n".join(f"- {s.title}：{s.url}" for s in sources)
            parts.append(f"【资料来源】\n{lines}")
        text = _clip("\n\n".join(parts), self._settings.research_context_max_chars)
        return ResearchOutcome(
            context_text=text,
            sources=sources,
            topic=(summary.topic_domain or "").strip(),
        )

    # ---------- 进程内 TTL 缓存（D4，风格对齐 TaskStore） ----------

    def _cache_key(
        self,
        user_input: str,
        user_id: int | None,
        kb_doc_ids: list[int] | None,
    ) -> str:
        # 清洗：去首尾与内部多余空白，让「同义输入」命中同一缓存；
        # 知识库内容因人而异，缓存按 用户/文档集合 加维度隔离
        normalized = " ".join(user_input.split())
        scope = ""
        if kb_doc_ids:
            docs = ",".join(str(i) for i in sorted(kb_doc_ids))
            scope = f"|u{user_id}|kb{docs}"
        return hashlib.sha256((normalized + scope).encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> ResearchOutcome | None:
        now = time.time()
        with self._lock:
            self._purge_expired(now)
            entry = self._cache.get(key)
            if entry is None:
                return None
            outcome, expires_at = entry
            if now >= expires_at:
                return None
            return outcome

    def _cache_put(self, key: str, outcome: ResearchOutcome) -> None:
        expires_at = time.time() + self._settings.research_cache_ttl_seconds
        with self._lock:
            self._cache[key] = (outcome, expires_at)

    def _purge_expired(self, now: float) -> None:
        """清理过期缓存项（调用方须已持锁）。"""
        expired = [k for k, (_, at) in self._cache.items() if now >= at]
        for k in expired:
            self._cache.pop(k, None)


# 全局单例（MVP 单进程，与 get_task_store 同风格）
_default_research: ResearchService | None = None


def get_research_service() -> ResearchService:
    global _default_research
    if _default_research is None:
        _default_research = ResearchService()
    return _default_research
