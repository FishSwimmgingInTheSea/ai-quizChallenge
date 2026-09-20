"""Prompt 模板契约测试：保证变量占位符稳定，接口调用方/测试基线不被破坏。"""

from __future__ import annotations

from app.prompts.quiz_prompt import (
    NO_RESEARCH_CONTEXT,
    QUIZ_PROMPT_VERSION,
    quiz_meta_prompt,
    quiz_question_prompt,
)
from app.prompts.report_prompt import REPORT_PROMPT_VERSION, report_prompt


def test_quiz_prompt_versions_present():
    assert QUIZ_PROMPT_VERSION == "quiz_prompt_v3"
    assert REPORT_PROMPT_VERSION == "report_prompt_v1"


def test_quiz_meta_prompt_inputs():
    assert set(quiz_meta_prompt.input_variables) == {"user_input", "research_context"}


def test_quiz_question_prompt_inputs():
    assert set(quiz_question_prompt.input_variables) == {
        "user_input",
        "research_context",
        "question_type",
        "difficulty",
        "index",
        "existing_stems",
    }


def test_quiz_meta_prompt_formats_without_error():
    msgs = quiz_meta_prompt.format_messages(
        user_input="学习 RAG",
        research_context=NO_RESEARCH_CONTEXT,
    )
    assert len(msgs) == 2
    assert "参考资料" in msgs[1].content


def test_quiz_question_prompt_formats_without_error():
    msgs = quiz_question_prompt.format_messages(
        user_input="学习 RAG",
        research_context=NO_RESEARCH_CONTEXT,
        question_type="single",
        difficulty="easy",
        index=2,
        existing_stems="- 第 1 题：RAG 的基本流程是什么？",
    )
    # system + user 两条消息
    assert len(msgs) == 2
    assert "single" in msgs[0].content
    assert "参考资料" in msgs[1].content


def test_quiz_question_prompt_dedup_zone_in_user_message():
    # v3：已出题目移入 user 消息的禁止重复区（system 弱位置的指令实测会被模型忽略）
    msgs = quiz_question_prompt.format_messages(
        user_input="学习 RAG",
        research_context=NO_RESEARCH_CONTEXT,
        question_type="single",
        difficulty="easy",
        index=2,
        existing_stems="- 第 1 题：RAG 的基本流程是什么？",
    )
    assert "禁止重复区" in msgs[1].content
    assert "RAG 的基本流程" in msgs[1].content
    assert "必须避开" in msgs[1].content
    # system 不再内嵌题目清单（改为多样性总则）
    assert "RAG 的基本流程" not in msgs[0].content
    assert "维度轮换" in msgs[0].content


def test_quiz_question_system_has_research_priority_rules():
    # v2 新增四条资料优先指令（D5）
    from app.prompts.quiz_prompt import QUIZ_QUESTION_SYSTEM

    assert "优先级高于" in QUIZ_QUESTION_SYSTEM
    assert "同名" in QUIZ_QUESTION_SYSTEM
    assert "不得编造" in QUIZ_QUESTION_SYSTEM
    assert "不得逐字复述" in QUIZ_QUESTION_SYSTEM


def test_report_prompt_inputs():
    assert set(report_prompt.input_variables) == {
        "topic",
        "quiz_json",
        "answer_records",
        "score_summary",
    }
