"""研究服务单测：mock 研究智能体，覆盖产出拼接、全路径降级、TTL 缓存与截断。"""

from __future__ import annotations

import asyncio

from app.core.config import Settings
from app.llm.output_schemas import ResearchSource, ResearchSummary
from app.services.research_service import ResearchService


def make_settings(**overrides) -> Settings:
    defaults = dict(
        _env_file=None,
        tavily_api_key="test-key",
        research_enabled=True,
        research_timeout=60,
        research_cache_ttl_seconds=900,
        research_context_max_chars=6000,
    )
    defaults.update(overrides)
    return Settings(**defaults)


class FakeAgent:
    """记录调用并可编程响应 / 异常 / 延迟的假研究智能体。"""

    def __init__(self, response=None, error=None, delay: float = 0.0):
        self.calls = 0
        self.payloads: list[dict] = []
        self.response = response
        self.error = error
        self.delay = delay

    async def ainvoke(self, payload: dict) -> dict:
        self.calls += 1
        self.payloads.append(payload)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.response


def make_summary(digest: str = "要点一；要点二", with_sources: bool = True) -> ResearchSummary:
    sources = (
        [ResearchSource(title="文档 A", url="https://a.com")] if with_sources else []
    )
    return ResearchSummary(
        topic_domain="主题属于 AI 编码智能体领域",
        context_digest=digest,
        sources=sources,
    )


def factory_of(*agents: FakeAgent):
    """依次返回各 agent 实例（每次 research 消耗一个，与真实工厂一致）。"""
    it = iter(agents)

    def factory():
        return next(it)

    return factory


# ---------- 正常产出 ----------
async def test_research_normal_output():
    agent = FakeAgent(response={"structured_response": make_summary()})
    service = ResearchService(factory_of(agent), settings=make_settings())
    outcome = await service.research("Harness Engineering")

    assert outcome.degraded is False
    assert "主题领域判定" in outcome.context_text
    assert "要点一" in outcome.context_text
    assert "https://a.com" in outcome.context_text
    assert outcome.sources[0].url == "https://a.com"
    # 智能体收到用户原始输入
    assert agent.payloads[0]["messages"][0][1] == "Harness Engineering"


async def test_research_summary_without_sources_still_ok():
    agent = FakeAgent(response={"structured_response": make_summary(with_sources=False)})
    service = ResearchService(factory_of(agent), settings=make_settings())
    outcome = await service.research("无来源主题")
    assert outcome.degraded is False
    assert outcome.sources == []
    assert "资料要点" in outcome.context_text


# ---------- 降级路径 ----------
async def test_research_timeout_degrades():
    agent = FakeAgent(delay=1.0)
    service = ResearchService(
        factory_of(agent), settings=make_settings(research_timeout=0.05)
    )
    outcome = await service.research("慢主题")
    assert outcome.degraded is True
    assert "超时" in outcome.degrade_reason
    assert outcome.context_text == ""


async def test_research_error_degrades():
    agent = FakeAgent(error=RuntimeError("mock agent 崩溃"))
    service = ResearchService(factory_of(agent), settings=make_settings())
    outcome = await service.research("任意主题")
    assert outcome.degraded is True
    assert "研究异常" in outcome.degrade_reason


async def test_research_empty_digest_degrades():
    agent = FakeAgent(response={"structured_response": make_summary(digest="   ")})
    service = ResearchService(factory_of(agent), settings=make_settings())
    outcome = await service.research("空资料主题")
    assert outcome.degraded is True
    assert "未产出有效资料" in outcome.degrade_reason


async def test_research_structured_response_missing_degrades():
    agent = FakeAgent(response={"messages": []})
    service = ResearchService(factory_of(agent), settings=make_settings())
    outcome = await service.research("无结构化输出")
    assert outcome.degraded is True


async def test_research_without_api_key_degrades_without_agent():
    agent = FakeAgent(response={"structured_response": make_summary()})
    service = ResearchService(
        factory_of(agent), settings=make_settings(tavily_api_key="")
    )
    outcome = await service.research("无 key")
    assert outcome.degraded is True
    assert "TAVILY_API_KEY" in outcome.degrade_reason
    # 未配置 key 时智能体根本不被构建
    assert agent.calls == 0


async def test_research_disabled_switch_degrades():
    agent = FakeAgent(response={"structured_response": make_summary()})
    service = ResearchService(
        factory_of(agent), settings=make_settings(research_enabled=False)
    )
    outcome = await service.research("关闭研究")
    assert outcome.degraded is True
    assert "RESEARCH_ENABLED" in outcome.degrade_reason
    assert agent.calls == 0


# ---------- 缓存 ----------
async def test_research_cache_hit_skips_second_run():
    agent = FakeAgent(response={"structured_response": make_summary()})
    service = ResearchService(factory_of(agent, agent), settings=make_settings())
    first = await service.research("缓存主题")
    second = await service.research("缓存主题")
    assert first.degraded is False and second.degraded is False
    # 第二次命中缓存：智能体只执行一次
    assert agent.calls == 1
    assert second.context_text == first.context_text


async def test_research_cache_normalizes_whitespace():
    agent = FakeAgent(response={"structured_response": make_summary()})
    service = ResearchService(factory_of(agent, agent), settings=make_settings())
    await service.research("缓存 主题")
    outcome = await service.research("  缓存\n主题  ")
    # 空白清洗后命中同一缓存
    assert agent.calls == 1
    assert outcome.degraded is False


async def test_research_failure_not_cached():
    bad = FakeAgent(error=RuntimeError("第一次失败"))
    good = FakeAgent(response={"structured_response": make_summary()})
    service = ResearchService(factory_of(bad, good), settings=make_settings())
    first = await service.research("先失败后成功")
    assert first.degraded is True
    second = await service.research("先失败后成功")
    # 降级不缓存：第二次重新执行研究并成功
    assert second.degraded is False
    assert bad.calls == 1 and good.calls == 1


async def test_research_cache_expires():
    agent = FakeAgent(response={"structured_response": make_summary()})
    service = ResearchService(
        factory_of(agent, agent),
        settings=make_settings(research_cache_ttl_seconds=0),
    )
    await service.research("过期主题")
    outcome = await service.research("过期主题")
    # TTL=0：第二次不命中缓存，重新研究
    assert agent.calls == 2
    assert outcome.degraded is False


# ---------- 拼接截断 ----------
async def test_research_context_truncated():
    digest = "长" * 8000
    agent = FakeAgent(response={"structured_response": make_summary(digest=digest)})
    service = ResearchService(
        factory_of(agent), settings=make_settings(research_context_max_chars=6000)
    )
    outcome = await service.research("超长资料主题")
    assert len(outcome.context_text) <= 6000
    assert "已截断" in outcome.context_text
