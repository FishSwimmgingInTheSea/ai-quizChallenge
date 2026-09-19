"""联网研究服务（quiz-web-search-grounding D1/D3/D4）。

出题前由研究智能体（create_agent + 双工具）自主检索与抓取资料，产出
结构化 ResearchSummary 并拼接为出题可用的 research_context。任何失败
路径（开关关闭 / 未配置 key / 超时 / 异常 / 无资料）均静默降级为纯模型
出题，任务不失败；研究产出带进程内 TTL 缓存（降级结果不缓存，避免一次
网络抖动导致后续请求长时间无资料）。
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

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.langchain_factory import get_research_model
from app.llm.output_schemas import ResearchSource, ResearchSummary
from app.llm.research_tools import _clip, build_research_tools

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


class ResearchProvider(Protocol):
    """联网研究提供方协议（预留博查 / Firecrawl 等替换扩展点）。"""

    async def research(self, user_input: str) -> "ResearchOutcome": ...


@dataclass
class ResearchOutcome:
    """研究产出（服务层对象，供出题链路消费）。"""

    context_text: str = ""
    sources: list[ResearchSource] = field(default_factory=list)
    degraded: bool = False
    degrade_reason: str = ""

    @classmethod
    def degraded_with(cls, reason: str) -> "ResearchOutcome":
        return cls(context_text="", sources=[], degraded=True, degrade_reason=reason)


def _build_research_agent() -> Any:
    """默认研究智能体：create_agent + 双工具 + 结构化收尾 + 双限次护栏（D1）。"""
    settings = get_settings()
    return create_agent(
        model=get_research_model(),
        tools=build_research_tools(settings),
        response_format=ResearchSummary,
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        middleware=[
            ToolCallLimitMiddleware(run_limit=settings.research_max_tool_calls),
            ModelCallLimitMiddleware(run_limit=settings.research_max_model_calls),
        ],
    )


class ResearchService:
    """联网研究服务：编排研究智能体、总超时与产出缓存。

    agent_factory 可注入（测试 mock 智能体）；默认工厂组装 create_agent
    官方路径。与 QuizGenerator 同构的注入模式。
    """

    def __init__(
        self,
        agent_factory: Callable[[], Any] | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._agent_factory = agent_factory or _build_research_agent
        self._cache: dict[str, tuple[ResearchOutcome, float]] = {}
        self._lock = threading.Lock()

    async def research(self, user_input: str) -> ResearchOutcome:
        """对用户输入执行联网研究；一切失败路径均降级，绝不抛异常。"""
        settings = self._settings
        if not settings.research_enabled:
            return ResearchOutcome.degraded_with("研究总开关关闭（RESEARCH_ENABLED=false）")
        if not settings.tavily_api_key:
            return ResearchOutcome.degraded_with("未配置 TAVILY_API_KEY，跳过联网研究")

        key = self._cache_key(user_input)
        cached = self._cache_get(key)
        if cached is not None:
            logger.info("研究缓存命中（key=%s…）", key[:10])
            return cached

        try:
            result = await asyncio.wait_for(
                self._agent_factory().ainvoke({"messages": [("user", user_input)]}),
                timeout=settings.research_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "研究超时（上限 %ss）：%s", settings.research_timeout, user_input[:50]
            )
            return ResearchOutcome.degraded_with(
                f"研究超时（>{settings.research_timeout}s）"
            )
        except Exception as exc:  # noqa: BLE001 - 一切研究侧异常均静默降级
            logger.warning("研究失败：%s", exc)
            return ResearchOutcome.degraded_with(f"研究异常：{exc}")

        summary = (
            result.get("structured_response") if isinstance(result, dict) else None
        )
        if not isinstance(summary, ResearchSummary) or not (
            summary.context_digest or ""
        ).strip():
            return ResearchOutcome.degraded_with("研究未产出有效资料")

        outcome = self._to_outcome(summary)
        self._cache_put(key, outcome)
        logger.info(
            "研究完成：来源 %d 条，资料 %d 字符",
            len(outcome.sources),
            len(outcome.context_text),
        )
        return outcome

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
        return ResearchOutcome(context_text=text, sources=sources)

    # ---------- 进程内 TTL 缓存（D4，风格对齐 TaskStore） ----------

    def _cache_key(self, user_input: str) -> str:
        # 清洗：去首尾与内部多余空白，让「同义输入」命中同一缓存
        normalized = " ".join(user_input.split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

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
