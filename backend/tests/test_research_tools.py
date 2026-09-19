"""研究工具单测：mock Tavily Wrapper，验证参数透传、边界校验、双层截断与降级文本。"""

from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.llm.research_tools import build_research_tools
from langchain_tavily._utilities import (
    TavilyExtractAPIWrapper,
    TavilySearchAPIWrapper,
)


class FakeSearchWrapper:
    """记录调用参数并返回预置响应的搜索 Wrapper。"""

    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self.calls: list[dict] = []
        self.response = response if response is not None else {"results": []}
        self.error = error

    async def raw_results_async(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class FakeExtractWrapper:
    """记录调用参数并返回预置响应的抓取 Wrapper。"""

    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self.calls: list[dict] = []
        self.response = response if response is not None else {"results": []}
        self.error = error

    async def raw_results_async(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def make_tools(
    search: FakeSearchWrapper | None = None, extract: FakeExtractWrapper | None = None
):
    settings = Settings(
        _env_file=None,
        tavily_api_key="test-key",
        research_results_limit=8,
        research_per_source_max_chars=2500,
        research_tool_output_max_chars=6000,
    )
    return build_research_tools(settings, search_wrapper=search, extract_wrapper=extract)


SEARCH_RESPONSE = {
    "query": "Harness Engineering",
    "answer": "Harness Engineering 指测试工程中的脚手架/线束工程概念。",
    "results": [
        {"title": "Result A", "url": "https://a.com", "content": "摘要 A", "score": 0.9},
        {"title": "Result B", "url": "https://b.com", "content": "摘要 B", "score": 0.8},
    ],
}


# ---------- 工具元信息 ----------
def test_tools_named_and_described():
    web_search, web_extract = make_tools()
    assert web_search.name == "web_search"
    assert web_extract.name == "web_extract"
    # 参数选择策略写入 docstring，模型可见
    assert "include_full_content" in web_search.description
    assert "网页" in web_extract.description


# ---------- web_search：参数透传 ----------
async def test_web_search_passes_dynamic_params():
    fake = FakeSearchWrapper(response=SEARCH_RESPONSE)
    web_search, _ = make_tools(search=fake)
    out = await web_search.ainvoke(
        {
            "query": "Harness Engineering",
            "max_results": 3,
            "country": "china",
            "time_range": "month",
            "search_depth": "basic",
        }
    )
    call = fake.calls[0]
    assert call["query"] == "Harness Engineering"
    assert call["max_results"] == 3
    assert call["country"] == "china"
    assert call["time_range"] == "month"
    assert call["search_depth"] == "basic"
    # 未请求全文时不开 raw_content / answer
    assert call.get("include_raw_content") is None
    assert call.get("include_answer") is None
    # 输出含来源标题与 URL
    assert "Result A" in out and "https://a.com" in out


async def test_web_search_full_content_upgrades_request():
    fake = FakeSearchWrapper(response=SEARCH_RESPONSE)
    web_search, _ = make_tools(search=fake)
    out = await web_search.ainvoke(
        {"query": "新术语", "include_full_content": True, "search_depth": "basic"}
    )
    call = fake.calls[0]
    assert call["include_raw_content"] is True
    assert call["include_answer"] is True
    # 全文模式强制 advanced 深度
    assert call["search_depth"] == "advanced"
    # 响应含 answer 时输出搜索摘要
    assert "【搜索摘要】" in out


async def test_web_search_passes_domain_filters():
    fake = FakeSearchWrapper(response=SEARCH_RESPONSE)
    web_search, _ = make_tools(search=fake)
    await web_search.ainvoke(
        {
            "query": "q",
            "include_domains": ["docs.python.org"],
            "exclude_domains": ["example.com"],
        }
    )
    call = fake.calls[0]
    assert call["include_domains"] == ["docs.python.org"]
    assert call["exclude_domains"] == ["example.com"]


# ---------- web_search：边界校验 ----------
async def test_web_search_max_results_bounds():
    fake = FakeSearchWrapper(response=SEARCH_RESPONSE)
    web_search, _ = make_tools(search=fake)
    with pytest.raises(ValidationError):
        await web_search.ainvoke({"query": "x", "max_results": 9})
    with pytest.raises(ValidationError):
        await web_search.ainvoke({"query": "x", "max_results": 0})
    # 校验失败不触达底层
    assert fake.calls == []


# ---------- web_search：截断 ----------
async def test_web_search_truncates_raw_content():
    fake = FakeSearchWrapper(
        response={
            "results": [
                {
                    "title": "T",
                    "url": "https://t.com",
                    "content": "c",
                    "raw_content": "x" * 3000,
                }
            ]
        }
    )
    web_search, _ = make_tools(search=fake)
    out = await web_search.ainvoke({"query": "q", "include_full_content": True})
    # 单源截断：全文不超过 2500 字符
    assert out.count("x") <= 2500
    assert "已截断" in out


async def test_web_search_total_output_budget():
    big = "x" * 3000
    fake = FakeSearchWrapper(
        response={
            "results": [
                {"title": f"T{i}", "url": f"https://t{i}.com", "content": big, "raw_content": big}
                for i in range(4)
            ]
        }
    )
    web_search, _ = make_tools(search=fake)
    out = await web_search.ainvoke({"query": "q", "include_full_content": True})
    # 整体输出不超过工具输出预算
    assert len(out) <= 6000


# ---------- web_search：降级与空结果 ----------
async def test_web_search_error_returns_degraded_text():
    fake = FakeSearchWrapper(error=RuntimeError("mock 网络错误"))
    web_search, _ = make_tools(search=fake)
    out = await web_search.ainvoke({"query": "q"})
    assert "暂时不可用" in out


async def test_web_search_empty_results_hint():
    fake = FakeSearchWrapper(response={"results": []})
    web_search, _ = make_tools(search=fake)
    out = await web_search.ainvoke({"query": "q"})
    assert "未检索到" in out


# ---------- 签名契约：包装工具必须传齐真实 Wrapper 的全部必传参数 ----------
# 背景：Wrapper 的 raw_results_async 参数无默认值（必传位置参数），宽松 **kwargs mock
# 掩盖过漏参问题（真实验收才暴露 400/TypeError），故用真实签名动态断言。
def _required_params(cls, method: str) -> list[str]:
    sig = inspect.signature(getattr(cls, method))
    return [
        p.name
        for p in sig.parameters.values()
        if p.default is inspect.Parameter.empty
        and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        and p.name != "self"
    ]


class StrictSearchWrapper:
    """严格签名 mock：漏传真实 Wrapper 必传参数时直接失败。"""

    def __init__(self):
        self.calls: list[dict] = []
        self.required = _required_params(TavilySearchAPIWrapper, "raw_results_async")

    async def raw_results_async(self, **kwargs):
        missing = [n for n in self.required if n not in kwargs]
        assert not missing, f"web_search 漏传 Wrapper 必传参数：{missing}"
        self.calls.append(kwargs)
        return SEARCH_RESPONSE


class StrictExtractWrapper:
    """严格签名 mock：漏传真实 Wrapper 必传参数时直接失败。"""

    def __init__(self):
        self.calls: list[dict] = []
        self.required = _required_params(TavilyExtractAPIWrapper, "raw_results_async")

    async def raw_results_async(self, **kwargs):
        missing = [n for n in self.required if n not in kwargs]
        assert not missing, f"web_extract 漏传 Wrapper 必传参数：{missing}"
        self.calls.append(kwargs)
        return EXTRACT_RESPONSE


async def test_web_search_covers_wrapper_required_params():
    fake = StrictSearchWrapper()
    web_search, _ = make_tools(search=fake)
    await web_search.ainvoke({"query": "签名契约"})
    assert fake.calls


async def test_web_extract_covers_wrapper_required_params():
    fake = StrictExtractWrapper()
    _, web_extract = make_tools(extract=fake)
    await web_extract.ainvoke({"urls": ["https://s.com"]})
    assert fake.calls


# ---------- web_extract ----------
EXTRACT_RESPONSE = {
    "results": [{"url": "https://doc.com/a", "raw_content": "正文内容 A" * 10}],
    "failed_results": [{"url": "https://bad.com", "error": "404 Not Found"}],
}


async def test_web_extract_passes_params():
    fake = FakeExtractWrapper(response=EXTRACT_RESPONSE)
    _, web_extract = make_tools(extract=fake)
    out = await web_extract.ainvoke(
        {"urls": ["https://doc.com/a"], "extract_depth": "advanced"}
    )
    call = fake.calls[0]
    assert call["urls"] == ["https://doc.com/a"]
    assert call["extract_depth"] == "advanced"
    assert "正文内容 A" in out
    # 失败 URL 也在输出中呈现
    assert "https://bad.com" in out
    assert "404" in out


async def test_web_extract_urls_bounds():
    fake = FakeExtractWrapper(response=EXTRACT_RESPONSE)
    _, web_extract = make_tools(extract=fake)
    with pytest.raises(ValidationError):
        await web_extract.ainvoke({"urls": [f"https://u{i}.com" for i in range(4)]})
    with pytest.raises(ValidationError):
        await web_extract.ainvoke({"urls": []})
    assert fake.calls == []


async def test_web_extract_truncates_content():
    fake = FakeExtractWrapper(
        response={"results": [{"url": "https://t.com", "raw_content": "y" * 3000}]}
    )
    _, web_extract = make_tools(extract=fake)
    out = await web_extract.ainvoke({"urls": ["https://t.com"]})
    assert out.count("y") <= 2500
    assert "已截断" in out


async def test_web_extract_error_returns_degraded_text():
    fake = FakeExtractWrapper(error=RuntimeError("mock 抓取失败"))
    _, web_extract = make_tools(extract=fake)
    out = await web_extract.ainvoke({"urls": ["https://x.com"]})
    assert "暂时不可用" in out


async def test_web_extract_all_failed_returns_unavailable():
    fake = FakeExtractWrapper(
        response={"results": [], "failed_results": [{"url": "https://x.com", "error": "403"}]}
    )
    _, web_extract = make_tools(extract=fake)
    out = await web_extract.ainvoke({"urls": ["https://x.com"]})
    # 全部失败时至少给出失败原因
    assert "403" in out
