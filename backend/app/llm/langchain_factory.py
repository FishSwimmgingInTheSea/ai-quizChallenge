"""LangChain 模型工厂：统一初始化对接 DeepSeek 的 ChatOpenAI。

方案 §7.2：使用 langchain-openai 的 ChatOpenAI，通过 base_url + api_key
对接 DeepSeek 的 OpenAI 兼容接口；出题/报告复用同一工厂，仅温度不同。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel

from app.core.config import Settings, get_settings


def _build_chat_model(temperature: float) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        temperature=temperature,
        max_tokens=settings.quiz_max_tokens,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
        top_p=settings.quiz_top_p,
        # deepseek-flash 默认开启思考模式，与结构化输出的强制 tool_choice 互斥
        # （400 "Thinking mode does not support this tool_choice"），显式禁用
        extra_body={"thinking": {"type": settings.deepseek_thinking}},
    )


@lru_cache
def get_quiz_model() -> ChatOpenAI:
    """出题模型（temperature 0.4）。"""
    return _build_chat_model(get_settings().quiz_temperature)


@lru_cache
def get_report_model() -> ChatOpenAI:
    """报告模型（temperature 0.5）。"""
    return _build_chat_model(get_settings().report_temperature)


@lru_cache
def get_research_model() -> ChatOpenAI:
    """研究模型（quiz-web-search-grounding D9，temperature 取 research_temperature，事实性优先低温）。"""
    return _build_chat_model(get_settings().research_temperature)


# ---------- 知识库向量模型（百炼 text-embedding-v4，OpenAI 兼容接口） ----------


def _build_embeddings(settings: Settings) -> OpenAIEmbeddings:
    """构建知识库 embedding 模型；未配置 key 时由 openai 客户端抛错（调用方先检查）。"""
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.embedding_base_url,
        dimensions=settings.embedding_dimensions,
        # 百炼单请求最多 10 条文本：批量自动分批上限
        chunk_size=settings.embedding_batch_size,
        # DashScope 非原生 OpenAI 端点：关闭 tiktoken 长度自查，
        # 否则嵌入请求会因本地分块逻辑报错（社区多案例验证的坑）
        check_embedding_ctx_length=False,
    )


@lru_cache
def get_embeddings() -> OpenAIEmbeddings:
    """知识库向量模型（全局单例）。"""
    return _build_embeddings(get_settings())


def with_structured_output(model: ChatOpenAI, schema: type[BaseModel]) -> Runnable[Any, Any]:
    """DeepSeek 当前不支持 OpenAI json_schema response_format，改用 function calling。"""
    return model.with_structured_output(schema, method="function_calling")
