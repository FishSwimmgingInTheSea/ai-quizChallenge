"""文生图封装（question-images）：百炼 qwen-image-2.0 同步生图 + httpx 下载。

- `build_image_prompt`：据题目内容构建生图提示词（纯函数，无外部依赖）。
- `DashScopeImageGenerator`：`MultiModalConversation.call` 为同步阻塞接口，
  经 `asyncio.to_thread` 下放工作线程；拿到 24h 临时 URL 后用 httpx 下载字节。
- 一切异常/超时均在 `generate` 内收敛为返回 None，由上层降级为不配图，
  绝不向出题主流程抛出。

qwen-image-2.0 关键事实（阿里云百炼官方文档核实）：仅支持同步接口，
响应结构 `output.choices[0].message.content[0].image` 为图片 URL，有效期 24h。
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.quiz import Question

logger = get_logger(__name__)

# 固定画面风格约束：简洁、无文字水印、适合学习卡片
_STYLE_SUFFIX = "简洁清晰的插画风格，白色背景，构图居中，适合学习卡片，画面中不出现任何文字，无水印"
# 风格约束关键词（供测试断言提示词确实带上了风格约束）
STYLE_KEYWORDS = ("白色背景", "不出现任何文字", "无水印", "插画风格")


def build_image_prompt(question: Question, *, max_len: int = 300) -> str:
    """据题目内容构建文生图提示词（纯函数）。

    以题干为核心，拼接知识点；选择题附带正确选项文本以引导具体画面
    （判断题的「正确/错误」选项无画面意义，故排除）。末尾追加固定风格
    约束，并整体截断到 max_len 以内。
    """
    parts: list[str] = []
    stem = (question.stem or "").strip()
    if stem:
        parts.append(stem)

    kp = (question.knowledge_point or "").strip()
    if kp and kp != "综合":
        parts.append(f"知识点：{kp}")

    if question.type in ("single", "multiple"):
        answer_keys = set(question.answer or [])
        correct = [o.text.strip() for o in question.options if o.key in answer_keys]
        correct = [c for c in correct if c]
        if correct:
            parts.append("、".join(correct))

    body = "，".join(parts).strip()
    # 预留风格后缀空间后截断题干主体，保证成品始终带风格约束且不超上限
    budget = max(max_len - len(_STYLE_SUFFIX) - 1, 1)
    if len(body) > budget:
        body = body[:budget]
    return f"{body}。{_STYLE_SUFFIX}"


def extract_image_url(response: Any) -> str | None:
    """从 DashScope 响应中提取图片临时 URL；结构缺失/失败返回 None。

    兼容 dict 与属性两种访问形态（SDK 返回对象字段可能是 dict 或属性）。
    """
    output = _get(response, "output")
    if not output:
        return None
    choices = _get(output, "choices")
    if not choices:
        return None
    message = _get(choices[0], "message")
    if not message:
        return None
    content = _get(message, "content")
    if not content:
        return None
    for item in content:
        url = _get(item, "image")
        if url:
            return url
    return None


def _get(obj: Any, key: str) -> Any:
    """dict 用 []，对象用 getattr，统一取值。"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


@runtime_checkable
class ImageGenerator(Protocol):
    """文生图器协议：据提示词产出图片字节；失败返回 None（可注入 Fake）。"""

    async def generate(self, prompt: str) -> bytes | None: ...


class DashScopeImageGenerator:
    """百炼 qwen-image-2.0 文生图器（同步接口 + to_thread 下放 + httpx 下载）。"""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        # transport 仅测试注入（httpx.MockTransport）；正式链路用默认传输
        self._transport = transport

    async def generate(self, prompt: str) -> bytes | None:
        """生图 + 下载，全程超时保护；任何异常收敛为 None。"""
        try:
            return await asyncio.wait_for(
                self._generate(prompt), timeout=self._settings.image_gen_timeout
            )
        except Exception as exc:  # noqa: BLE001 - 生图失败一律降级，不冒泡
            logger.warning("文生图失败（降级为不配图）：%s", exc)
            return None

    async def _generate(self, prompt: str) -> bytes | None:
        url = await asyncio.to_thread(self._call_dashscope, prompt)
        if not url:
            return None
        return await self._download(url)

    def _call_dashscope(self, prompt: str) -> str | None:
        """同步调用百炼文生图，返回图片临时 URL；非 200 或无图返回 None。"""
        import dashscope  # noqa: F401  惰性导入：未启用配图时不加载 SDK
        from dashscope import MultiModalConversation

        s = self._settings
        response = MultiModalConversation.call(
            api_key=s.dashscope_api_key,
            model=s.dashscope_image_model,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            result_format="message",
            stream=False,
            n=1,
            size=s.image_size,
            negative_prompt=s.image_negative_prompt,
            watermark=False,
            prompt_extend=True,
        )
        status = getattr(response, "status_code", None)
        if status != 200:
            logger.warning(
                "文生图接口返回非 200：status=%s code=%s message=%s",
                status,
                getattr(response, "code", None),
                getattr(response, "message", None),
            )
            return None
        return extract_image_url(response)

    async def _download(self, url: str) -> bytes | None:
        """下载 24h 临时图片为字节；失败返回 None。"""
        async with httpx.AsyncClient(
            timeout=self._settings.image_gen_timeout, transport=self._transport
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
