"""用户输入清洗与长度校验。"""

from __future__ import annotations

import re

from app.core.config import get_settings
from app.core.exceptions import InvalidInputError

_WS_RE = re.compile(r"\s+")


def clean_input(text: str) -> str:
    """去首尾空白、折叠连续空白。"""
    if text is None:
        return ""
    return _WS_RE.sub(" ", text).strip()


def validate_length(text: str) -> str:
    """校验清洗后的输入长度，返回清洗后的文本。"""
    settings = get_settings()
    cleaned = clean_input(text)
    length = len(cleaned)
    if length < settings.input_min_len:
        raise InvalidInputError(
            f"输入内容太短了，至少 {settings.input_min_len} 个字"
        )
    if length > settings.input_max_len:
        raise InvalidInputError(
            f"输入内容太长了，最多 {settings.input_max_len} 个字"
        )
    return cleaned
