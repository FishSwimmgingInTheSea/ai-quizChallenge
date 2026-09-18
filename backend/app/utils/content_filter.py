"""敏感词过滤（MVP 本地词表版，方案 §14.2 的输入侧预检）。

上线前应在服务端补接微信 security.msgSecCheck 做二次检测。
"""

from __future__ import annotations

# MVP 极简本地词表，可按需扩充 / 外置为配置文件。
DEFAULT_SENSITIVE_WORDS: tuple[str, ...] = (
    "暴力", "色情", "赌博", "毒品", "枪支", "诈骗", "邪教",
)


def find_sensitive_words(
    text: str, words: tuple[str, ...] = DEFAULT_SENSITIVE_WORDS
) -> list[str]:
    if not text:
        return []
    return [w for w in words if w in text]


def contains_sensitive(
    text: str, words: tuple[str, ...] = DEFAULT_SENSITIVE_WORDS
) -> bool:
    return bool(find_sensitive_words(text, words))
