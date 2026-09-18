"""输入清洗、长度校验、敏感词过滤测试。"""

from __future__ import annotations

import pytest

from app.core.exceptions import InvalidInputError
from app.utils.content_filter import contains_sensitive, find_sensitive_words
from app.utils.id_generator import new_quiz_id, new_task_id, question_id
from app.utils.text_cleaner import clean_input, validate_length


def test_clean_input_collapses_whitespace():
    assert clean_input("  你好   世界 \n RAG ") == "你好 世界 RAG"


def test_validate_length_too_short():
    with pytest.raises(InvalidInputError):
        validate_length(" 1 ")


def test_validate_length_too_long():
    with pytest.raises(InvalidInputError):
        validate_length("学" * 600)


def test_validate_length_ok_returns_cleaned():
    assert validate_length("  什么是 RAG  ") == "什么是 RAG"


def test_sensitive_word_detection():
    assert contains_sensitive("这里涉及赌博内容") is True
    assert find_sensitive_words("正常学习内容") == []


def test_id_generator_prefixes():
    assert new_task_id().startswith("task_")
    assert new_quiz_id().startswith("quiz_")
    assert question_id(3) == "q3"
