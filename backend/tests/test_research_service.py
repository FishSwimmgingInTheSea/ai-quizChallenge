"""研究服务单测：mock 研究智能体，覆盖产出拼接、全路径降级、TTL 缓存与截断。"""

from __future__ import annotations

import asyncio

from app.core.config import Settings
from app.llm.output_schemas import ResearchSource, ResearchSummary
from app.services.research_service import ResearchService, system_prompt_for
from tests.conftest import FakeKbStore


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
    """依次返回各 agent 实例（每次 research 消耗一个，与真实工厂一致）。

    接受并记录 kwargs（user_id / kb_doc_ids），供断言服务层向工厂传参。
    """
    it = iter(agents)

    def factory(**kwargs):
        factory.last_kwargs = kwargs
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


# ---------- 知识库扩展（kb-rag：带参工厂 / 缓存隔离 / 提示词） ----------


def make_kb_settings(**overrides) -> Settings:
    defaults = dict(
        _env_file=None,
        tavily_api_key="test-key",
        research_enabled=True,
        research_timeout=60,
        research_cache_ttl_seconds=900,
        research_context_max_chars=6000,
        kb_enabled=True,
        dashscope_api_key="sk-test",
    )
    defaults.update(overrides)
    return Settings(**defaults)


async def test_research_with_kb_passes_factory_args():
    agent = FakeAgent(response={"structured_response": make_summary()})
    factory = factory_of(agent)
    service = ResearchService(factory, settings=make_kb_settings())
    outcome = await service.research("员工手册考核", user_id=7, kb_doc_ids=[3])
    assert outcome.degraded is False
    # 工厂收到用户与文档集合（用于构建 kb_search 工具）
    assert factory.last_kwargs == {"user_id": 7, "kb_doc_ids": [3]}
    # 用户原始输入不变地进入 agent
    assert agent.payloads[0]["messages"][0][1] == "员工手册考核"


async def test_research_without_kb_passes_none_factory_args():
    agent = FakeAgent(response={"structured_response": make_summary()})
    factory = factory_of(agent)
    service = ResearchService(factory, settings=make_kb_settings())
    await service.research("普通主题")
    # 未选知识库：工厂参数全 None，与原有代码路径一致
    assert factory.last_kwargs == {"user_id": None, "kb_doc_ids": None}


async def test_research_kb_without_tavily_key_still_runs():
    agent = FakeAgent(response={"structured_response": make_summary()})
    service = ResearchService(
        factory_of(agent), settings=make_kb_settings(tavily_api_key="")
    )
    outcome = await service.research("私有主题", user_id=7, kb_doc_ids=[3])
    # 无联网 key 但选了知识库：agent 仍构建运行（仅带 kb_search 工具）
    assert outcome.degraded is False
    assert agent.calls == 1


async def test_research_kb_unavailable_with_web_still_runs():
    # dashscope 未配但 tavily 有：静默忽略知识库，继续纯联网（降级策略）
    agent = FakeAgent(response={"structured_response": make_summary()})
    factory = factory_of(agent)
    service = ResearchService(
        factory, settings=make_kb_settings(dashscope_api_key="")
    )
    outcome = await service.research("主题", user_id=7, kb_doc_ids=[3])
    assert outcome.degraded is False
    assert agent.calls == 1
    assert factory.last_kwargs == {"user_id": None, "kb_doc_ids": None}


async def test_research_kb_disabled_switch_ignores_kb():
    agent = FakeAgent(response={"structured_response": make_summary()})
    factory = factory_of(agent)
    service = ResearchService(
        factory, settings=make_kb_settings(kb_enabled=False)
    )
    outcome = await service.research("主题", user_id=7, kb_doc_ids=[3])
    assert outcome.degraded is False
    assert factory.last_kwargs == {"user_id": None, "kb_doc_ids": None}


async def test_research_kb_without_user_or_providers_degrades():
    agent = FakeAgent(response={"structured_response": make_summary()})
    service = ResearchService(
        factory_of(agent),
        settings=make_kb_settings(tavily_api_key="", dashscope_api_key=""),
    )
    outcome = await service.research("私有主题", user_id=7, kb_doc_ids=[3])
    # 联网与知识库都不可用：降级且 agent 不被构建
    assert outcome.degraded is True
    assert "TAVILY_API_KEY" in outcome.degrade_reason
    assert agent.calls == 0


async def test_research_kb_doc_ids_without_user_ignored():
    agent = FakeAgent(response={"structured_response": make_summary()})
    service = ResearchService(
        factory_of(agent), settings=make_kb_settings(tavily_api_key="")
    )
    # user_id=None 时无法定位知识库：选择被忽略，与纯联网降级路径一致
    outcome = await service.research("主题", kb_doc_ids=[3])
    assert outcome.degraded is True
    assert agent.calls == 0


# ---------- 缓存按 用户/文档集合 隔离 ----------
async def test_research_cache_scoped_by_user():
    agent = FakeAgent(response={"structured_response": make_summary()})
    service = ResearchService(factory_of(agent, agent), settings=make_kb_settings())
    first = await service.research("同一主题", user_id=1, kb_doc_ids=[2])
    second = await service.research("同一主题", user_id=9, kb_doc_ids=[2])
    # 不同用户的知识库内容不同：缓存按 user 维度隔离，各自真实执行
    assert first.degraded is False and second.degraded is False
    assert agent.calls == 2


async def test_research_cache_scoped_by_kb_doc_ids():
    agent = FakeAgent(response={"structured_response": make_summary()})
    service = ResearchService(factory_of(agent, agent), settings=make_kb_settings())
    await service.research("同一主题", user_id=1, kb_doc_ids=[2])
    await service.research("同一主题", user_id=1, kb_doc_ids=[2, 5])
    # 文档集合不同：不共享缓存
    assert agent.calls == 2


async def test_research_cache_hit_same_user_and_docs():
    agent = FakeAgent(response={"structured_response": make_summary()})
    service = ResearchService(factory_of(agent, agent), settings=make_kb_settings())
    await service.research("同一主题", user_id=1, kb_doc_ids=[2])
    outcome = await service.research("同一主题", user_id=1, kb_doc_ids=[2])
    # 同用户同文档集合：命中缓存
    assert agent.calls == 1
    assert outcome.degraded is False


# ---------- 系统提示词条件化 ----------
def test_system_prompt_kb_addendum():
    base = system_prompt_for(with_kb=False)
    assert "kb_search" not in base
    with_kb = system_prompt_for(with_kb=True)
    assert "kb_search" in with_kb
    # 原有联网指引完整保留
    assert with_kb.startswith(base)


# ---------- 自动出题（空输入 + 知识库：概览注入 / 降级兜底 / topic 产出） ----------


def overview_docs() -> list:
    from langchain_core.documents import Document

    return [
        Document(
            page_content="员工手册第一条：入职培训三天",
            metadata={"doc_id": 3, "filename": "handbook.txt"},
        )
    ]


async def test_research_auto_mode_injects_overview_into_agent_message():
    agent = FakeAgent(response={"structured_response": make_summary()})
    kb = FakeKbStore(sample_docs=overview_docs())
    service = ResearchService(
        factory_of(agent), settings=make_kb_settings(), kb_store=kb
    )
    outcome = await service.research("", user_id=7, kb_doc_ids=[3])

    assert outcome.degraded is False
    assert kb.sample_calls == [(7, (3,), 2)]
    msg = agent.payloads[0]["messages"][0][1]
    # 文档概览原文与自动出题指令进入用户消息，agent 据此自推主题
    assert "员工手册第一条" in msg
    assert "自动出题" in msg
    # 推断主题随产出返回，供出题 prompt 兜底使用
    assert outcome.topic == "主题属于 AI 编码智能体领域"


async def test_research_auto_mode_empty_overview_degrades_without_agent():
    agent = FakeAgent(response={"structured_response": make_summary()})
    kb = FakeKbStore(sample_docs=[])
    service = ResearchService(
        factory_of(agent), settings=make_kb_settings(), kb_store=kb
    )
    outcome = await service.research("", user_id=7, kb_doc_ids=[3])
    # 概览为空（文档无 chunks）：降级且 agent 不被构建
    assert outcome.degraded is True
    assert "概览" in outcome.degrade_reason
    assert agent.calls == 0


async def test_research_auto_mode_agent_failure_falls_back_to_overview():
    agent = FakeAgent(error=RuntimeError("mock agent 崩溃"))
    kb = FakeKbStore(sample_docs=overview_docs())
    service = ResearchService(
        factory_of(agent), settings=make_kb_settings(), kb_store=kb
    )
    outcome = await service.research("", user_id=7, kb_doc_ids=[3])
    assert outcome.degraded is True
    assert "回退文档概览" in outcome.degrade_reason
    # 出题资料兜底为概览原文：自动出题承诺不落空
    assert "员工手册第一条" in outcome.context_text


async def test_research_non_auto_mode_message_unchanged():
    # 回归：非空输入时 agent 仍收用户原文，不取概览、不拼指令
    agent = FakeAgent(response={"structured_response": make_summary()})
    kb = FakeKbStore(sample_docs=overview_docs())
    service = ResearchService(
        factory_of(agent), settings=make_kb_settings(), kb_store=kb
    )
    await service.research("员工手册考核", user_id=7, kb_doc_ids=[3])
    assert agent.payloads[0]["messages"][0][1] == "员工手册考核"
    assert kb.sample_calls == []
