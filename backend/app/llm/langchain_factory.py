"""LangChain 模型工厂：统一初始化对接 DeepSeek 的 ChatOpenAI。

方案 §7.2：使用 langchain-openai 的 ChatOpenAI，通过 base_url + api_key
对接 DeepSeek 的 OpenAI 兼容接口；出题/报告复用同一工厂，仅温度不同。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.core.config import get_settings


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
    )


@lru_cache
def get_quiz_model() -> ChatOpenAI:
    """出题模型（temperature 0.4）。"""
    return _build_chat_model(get_settings().quiz_temperature)


@lru_cache
def get_report_model() -> ChatOpenAI:
    """报告模型（temperature 0.5）。"""
    return _build_chat_model(get_settings().report_temperature)


def with_structured_output(model: ChatOpenAI, schema: type[BaseModel]) -> Runnable[Any, Any]:
    """DeepSeek 当前不支持 OpenAI json_schema response_format，改用 function calling。"""
    return model.with_structured_output(schema, method="function_calling")
