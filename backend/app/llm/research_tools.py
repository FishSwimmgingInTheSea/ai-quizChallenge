"""联网研究工具（quiz-web-search-grounding D2）。

自定义 @tool 包装工具：官方 TavilySearch/TavilyExtract 工具在调用时锁定
include_answer / include_raw_content，且 max_results / country 不在调用时
动态参数清单，无法满足「复杂知识取全文、动态条数与地区」的需求。因此经
langchain-tavily 自带的 API Wrapper（不依赖 tavily-python，aiohttp 直连）
把上述参数显式暴露进工具 args schema；包装层做双层截断（单源 / 单工具
输出），实现官方限制防上下文爆炸的等效初衷。工具异常返回降级文本而非
抛异常，由 agent 自行决定换路或收尾，服务层另有整体降级兜底。
"""

from __future__ import annotations

from typing import Literal

from langchain_core.tools import BaseTool, tool
from langchain_tavily._utilities import (
    TavilyExtractAPIWrapper,
    TavilySearchAPIWrapper,
)
from pydantic import Field

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Tavily country 参数为国家级地区枚举（仅 topic=general 生效，值为小写国家
# 全称）；此处暴露兼顾国内外用户的常用子集，其余可不传（默认全球混合）
_Country = Literal[
    "china",
    "united states",
    "united kingdom",
    "canada",
    "australia",
    "germany",
    "france",
    "japan",
    "south korea",
    "singapore",
    "india",
    "russia",
]

# 工具不可用时的降级文本：不抛异常，让 agent 自行决定换路或直接收尾
_SEARCH_UNAVAILABLE = (
    "（搜索工具暂时不可用，可能是网络波动或配额限制。"
    "可换个关键词或放宽参数重试一次；仍失败请基于已有信息直接收尾。）"
)
_EXTRACT_UNAVAILABLE = (
    "（网页抓取工具暂时不可用，可能是网络波动或配额限制。"
    "可稍后重试一次；仍失败请基于已有信息直接收尾。）"
)
_TRUNCATED_MARK = "…（内容过长，已截断）"


def _clip(text: str, limit: int) -> str:
    """按字符数截断到预算内，超限附标记。"""
    if len(text) <= limit:
        return text
    keep = max(limit - len(_TRUNCATED_MARK), 1)
    return text[:keep] + _TRUNCATED_MARK


def build_research_tools(
    settings: Settings,
    *,
    search_wrapper: TavilySearchAPIWrapper | None = None,
    extract_wrapper: TavilyExtractAPIWrapper | None = None,
) -> list[BaseTool]:
    """构造 web_search / web_extract 两个研究工具。

    wrapper 可注入（测试 mock）；正式链路由 research_service 持有调用。
    """

    max_results_limit = settings.research_results_limit
    per_source_limit = settings.research_per_source_max_chars
    output_limit = settings.research_tool_output_max_chars
    search = search_wrapper or TavilySearchAPIWrapper(
        tavily_api_key=settings.tavily_api_key
    )
    extract = extract_wrapper or TavilyExtractAPIWrapper(
        tavily_api_key=settings.tavily_api_key
    )

    @tool
    async def web_search(
        query: str,
        search_depth: Literal["basic", "advanced"] = "basic",
        max_results: int = Field(default=5, ge=1, le=max_results_limit),
        time_range: Literal["day", "week", "month", "year"] | None = None,
        country: _Country | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        include_full_content: bool = False,
    ) -> str:
        """联网搜索公开资料，返回带来源标题与 URL 的结果文本。

        参数选择策略（自主判断，不必询问用户）：
        - 复杂、冷门或新兴主题（新术语、跨领域同名词、版本敏感的技术）：
          search_depth="advanced" 并 include_full_content=True，直接取回完整正文；
        - 简单、常见主题：默认参数即可，标题加摘要通常足够；
        - 中文主题建议 country="china"，英文主题可不传（全球混合）或选对应国家；
        - max_results 按需调整：确认术语含义 1~3 条足够，需覆盖多个侧面时 5 条以上；
        - 追踪近期动态时配合 time_range（day/week/month/year）。

        Args:
            query: 检索关键词，建议用主题的核心术语，必要时附加上下文限定词。
            search_depth: 检索深度，advanced 更全面但更慢。
            max_results: 返回结果条数。
            time_range: 结果时间范围过滤。
            country: 地区偏好（国家级，仅 general 主题生效）。
            include_domains: 仅在这些域名内检索。
            exclude_domains: 排除这些域名。
            include_full_content: 结果附带页面完整正文（已按预算截断）。
        """
        try:
            raw = await search.raw_results_async(
                query=query,
                max_results=max_results,
                search_depth="advanced" if include_full_content else search_depth,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
                include_answer=True if include_full_content else None,
                include_raw_content=True if include_full_content else None,
                time_range=time_range,
                country=country,
                # Wrapper 签名为无默认值的必传位置参数，未暴露给模型的项一律 None
                include_images=None,
                include_image_descriptions=None,
                include_favicon=None,
                topic=None,
                auto_parameters=None,
                start_date=None,
                end_date=None,
                include_usage=None,
                exact_match=None,
            )
        except Exception as exc:  # noqa: BLE001 - 工具失败降级为文本，agent 自行决策
            logger.warning(
                "web_search 调用失败（query=%r, country=%s）：%s", query, country, exc
            )
            return _SEARCH_UNAVAILABLE

        sections: list[str] = []
        answer = raw.get("answer")
        if answer:
            sections.append(f"【搜索摘要】{answer}")
        for i, item in enumerate(raw.get("results") or [], start=1):
            title = item.get("title") or "（无标题）"
            url = item.get("url") or ""
            content = item.get("content") or ""
            block = f"【结果 {i}】{title}\n来源：{url}\n摘要：{content}"
            raw_content = item.get("raw_content")
            if raw_content:
                block += f"\n全文：{_clip(raw_content, per_source_limit)}"
            sections.append(block)
        if not sections:
            return (
                f"（未检索到与「{query}」相关的结果。建议更换关键词、"
                "放宽 time_range/country 参数，或改用 web_extract 抓取具体网页。）"
            )
        return _clip("\n\n".join(sections), output_limit)

    @tool
    async def web_extract(
        urls: list[str] = Field(min_length=1, max_length=3),
        extract_depth: Literal["basic", "advanced"] = "basic",
    ) -> str:
        """按网址抓取整个页面的正文内容，返回带 URL 的全文文本。

        当用户输入或上下文中出现网页链接时优先使用本工具（先抓正文，
        再按需补充搜索）。

        Args:
            urls: 要抓取的网页地址列表，一次最多 3 个。
            extract_depth: 抓取深度；结构复杂或反爬严格的站点（如 LinkedIn、
                YouTube）建议 "advanced"。
        """
        try:
            raw = await extract.raw_results_async(
                urls=list(urls),
                extract_depth=extract_depth,
                # Wrapper 签名为无默认值的必传位置参数，未暴露给模型的项一律 None
                include_images=None,
                include_favicon=None,
                format=None,
                include_usage=None,
                query=None,
                chunks_per_source=None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("web_extract 调用失败（urls=%s）：%s", urls, exc)
            return _EXTRACT_UNAVAILABLE

        sections: list[str] = []
        for item in raw.get("results") or []:
            url = item.get("url") or ""
            content = item.get("raw_content") or ""
            sections.append(f"【页面】{url}\n{_clip(content, per_source_limit)}")
        for item in raw.get("failed_results") or []:
            sections.append(
                f"【抓取失败】{item.get('url', '')}：{item.get('error', '未知原因')}"
            )
        if not sections:
            return _EXTRACT_UNAVAILABLE
        return _clip("\n\n".join(sections), output_limit)

    return [web_search, web_extract]
