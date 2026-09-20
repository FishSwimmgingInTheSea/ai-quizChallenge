"""生图提示词构建纯函数测试（question-images 任务 3.1）。"""

from __future__ import annotations

from app.llm.image_gen import STYLE_KEYWORDS, build_image_prompt
from app.models.quiz import Option, Question


def _question(**overrides) -> Question:
    base = dict(
        id="q1",
        type="single",
        stem="苹果对应的英文单词是下列哪一个？",
        options=[
            Option(key="A", text="apple"),
            Option(key="B", text="banana"),
        ],
        answer=["A"],
        explanation="apple 意为苹果。",
        knowledge_point="英语单词",
        difficulty="easy",
    )
    base.update(overrides)
    return Question(**base)


def test_prompt_包含题干与知识点():
    prompt = build_image_prompt(_question())
    assert "苹果" in prompt
    assert "英语单词" in prompt


def test_prompt_含固定风格约束():
    prompt = build_image_prompt(_question())
    # 风格后缀的关键约束词必须出现（无文字、无水印等）
    assert any(kw in prompt for kw in STYLE_KEYWORDS)


def test_prompt_单选题带正确选项文本():
    prompt = build_image_prompt(_question())
    assert "apple" in prompt


def test_prompt_判断题不污染正确错误字样():
    q = _question(
        type="judge",
        stem="苹果是一种蔬菜。",
        options=[Option(key="A", text="正确"), Option(key="B", text="错误")],
        answer=["B"],
        knowledge_point="常识辨析",
    )
    prompt = build_image_prompt(q)
    assert "正确" not in prompt
    assert "错误" not in prompt


def test_prompt_超长被截断到上限():
    long_stem = "这是一个非常长的题干" * 200
    q = _question(stem=long_stem)
    prompt = build_image_prompt(q, max_len=120)
    assert len(prompt) <= 120
    # 截断后仍保留风格约束
    assert any(kw in prompt for kw in STYLE_KEYWORDS)
