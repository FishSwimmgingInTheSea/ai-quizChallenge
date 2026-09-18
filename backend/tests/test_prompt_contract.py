"""Prompt 模板契约测试：保证变量占位符稳定，接口调用方/测试基线不被破坏。"""

from __future__ import annotations

from app.prompts.quiz_prompt import (
    QUIZ_PROMPT_VERSION,
    quiz_meta_prompt,
    quiz_question_prompt,
)
from app.prompts.report_prompt import REPORT_PROMPT_VERSION, report_prompt


def test_quiz_prompt_versions_present():
    assert QUIZ_PROMPT_VERSION == "quiz_prompt_v1"
    assert REPORT_PROMPT_VERSION == "report_prompt_v1"


def test_quiz_meta_prompt_inputs():
    assert set(quiz_meta_prompt.input_variables) == {"user_input"}


def test_quiz_question_prompt_inputs():
    assert set(quiz_question_prompt.input_variables) == {
        "user_input",
        "question_type",
        "difficulty",
        "index",
        "existing_stems",
    }


def test_quiz_question_prompt_formats_without_error():
    msgs = quiz_question_prompt.format_messages(
        user_input="学习 RAG",
        question_type="single",
        difficulty="easy",
        index=1,
        existing_stems="（暂无）",
    )
    # system + user 两条消息
    assert len(msgs) == 2
    assert "single" in msgs[0].content


def test_report_prompt_inputs():
    assert set(report_prompt.input_variables) == {
        "topic",
        "quiz_json",
        "answer_records",
        "score_summary",
    }
