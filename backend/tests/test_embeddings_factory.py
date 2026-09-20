"""知识库 Embedding 工厂测试：验证对接百炼的关键参数（不发真实请求）。"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.llm.langchain_factory import _build_embeddings


def _settings(**overrides) -> Settings:
    defaults = dict(
        _env_file=None,
        dashscope_api_key="sk-test-dashscope",
        embedding_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        embedding_model="text-embedding-v4",
        embedding_dimensions=1024,
        embedding_batch_size=10,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_embeddings_params():
    emb = _build_embeddings(_settings())
    assert emb.model == "text-embedding-v4"
    assert emb.dimensions == 1024
    # 百炼非原生 OpenAI 端点：必须关闭 tiktoken 长度自查
    assert emb.check_embedding_ctx_length is False
    # 百炼单请求最多 10 条文本：批量分批上限
    assert emb.chunk_size == 10


def test_embeddings_custom_dimensions():
    emb = _build_embeddings(_settings(embedding_dimensions=768))
    assert emb.dimensions == 768


def test_embeddings_empty_key_raises():
    """未配置 DASHSCOPE_API_KEY 时应显式失败（调用方先检查并给出友好错误）。"""
    with pytest.raises(Exception):
        _build_embeddings(_settings(dashscope_api_key=""))
