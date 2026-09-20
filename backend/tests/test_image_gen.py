"""文生图封装测试（question-images 任务 3.2）：Mock dashscope + httpx，不触真实网络。"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.llm.image_gen import DashScopeImageGenerator, extract_image_url


class _FakeResponse:
    def __init__(self, status_code=200, image_url=None, code="", message=""):
        self.status_code = status_code
        self.code = code
        self.message = message
        if image_url is not None:
            self.output = {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": [{"image": image_url}],
                        },
                    }
                ]
            }
        else:
            self.output = {"choices": []}


@pytest.fixture
def settings() -> Settings:
    return Settings(
        dashscope_api_key="sk-test",
        image_gen_enabled=True,
        cos_secret_id="id",
        cos_secret_key="key",
        cos_bucket="b-123",
        cos_region="ap-guangzhou",
    )


# ---------- extract_image_url 解析 ----------


def test_extract_成功解析文档响应结构():
    resp = _FakeResponse(image_url="https://oss/x.png?Expires=1")
    assert extract_image_url(resp) == "https://oss/x.png?Expires=1"


def test_extract_无choices返回None():
    assert extract_image_url(_FakeResponse(image_url=None)) is None


def test_extract_output为None返回None():
    class R:
        status_code = 200
        output = None

    assert extract_image_url(R()) is None


# ---------- _call_dashscope ----------


def test_call_状态200返回URL(monkeypatch, settings):
    monkeypatch.setattr(
        "dashscope.MultiModalConversation.call",
        lambda **kw: _FakeResponse(image_url="https://oss/a.png"),
    )
    gen = DashScopeImageGenerator(settings)
    assert gen._call_dashscope("一只猫") == "https://oss/a.png"


def test_call_非200返回None(monkeypatch, settings):
    monkeypatch.setattr(
        "dashscope.MultiModalConversation.call",
        lambda **kw: _FakeResponse(status_code=400, code="InvalidParameter", message="x"),
    )
    gen = DashScopeImageGenerator(settings)
    assert gen._call_dashscope("一只猫") is None


def test_call_传入模型与尺寸参数(monkeypatch, settings):
    captured = {}

    def fake(**kw):
        captured.update(kw)
        return _FakeResponse(image_url="https://oss/a.png")

    monkeypatch.setattr("dashscope.MultiModalConversation.call", fake)
    DashScopeImageGenerator(settings)._call_dashscope("一只猫")
    assert captured["model"] == "qwen-image-2.0"
    assert captured["size"] == "512*512"
    assert captured["api_key"] == "sk-test"
    assert captured["messages"][0]["content"][0]["text"] == "一只猫"


# ---------- generate 端到端（生图 + 下载） ----------


async def test_generate_成功返回字节(monkeypatch, settings):
    monkeypatch.setattr(
        "dashscope.MultiModalConversation.call",
        lambda **kw: _FakeResponse(image_url="https://oss/a.png"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\x89PNG-fake-bytes")

    gen = DashScopeImageGenerator(settings, transport=httpx.MockTransport(handler))
    assert await gen.generate("一只猫") == b"\x89PNG-fake-bytes"


async def test_generate_生图抛错返回None(monkeypatch, settings):
    def boom(**kw):
        raise RuntimeError("网络异常")

    monkeypatch.setattr("dashscope.MultiModalConversation.call", boom)
    gen = DashScopeImageGenerator(settings)
    assert await gen.generate("一只猫") is None


async def test_generate_下载失败返回None(monkeypatch, settings):
    monkeypatch.setattr(
        "dashscope.MultiModalConversation.call",
        lambda **kw: _FakeResponse(image_url="https://oss/a.png"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    gen = DashScopeImageGenerator(settings, transport=httpx.MockTransport(handler))
    assert await gen.generate("一只猫") is None


async def test_generate_无图URL返回None(monkeypatch, settings):
    monkeypatch.setattr(
        "dashscope.MultiModalConversation.call",
        lambda **kw: _FakeResponse(image_url=None),
    )
    gen = DashScopeImageGenerator(settings)
    assert await gen.generate("一只猫") is None
