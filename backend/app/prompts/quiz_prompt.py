"""出题 Prompt（版本化，方案 §8.2/§8.3/§8.7）。

MVP 采用"单题循环生成"：每次只让模型产出 1 道题，JSON 更小、截断风险更低。
另有一个 meta prompt 用于生成题库标题与摘要。
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

QUIZ_PROMPT_VERSION = "quiz_prompt_v2"

# 出题无资料时传入的固定占位文本（quiz-web-search-grounding D5）
NO_RESEARCH_CONTEXT = "（本次未获取到检索资料）"

# ---------- 题库元信息（标题 + 摘要） ----------
QUIZ_META_SYSTEM = (
    "你是一名专业的 AI 学习教练。请根据用户想学习的内容，"
    "为一套闯关答题题库拟定一个简洁有趣的标题和一句主题摘要。"
    "标题不超过 15 个字，摘要不超过 40 个字，风格轻松、贴近小程序阅读。"
    "若用户消息附有参考资料，标题与摘要须锚定资料确认的主题领域。"
)

quiz_meta_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", QUIZ_META_SYSTEM),
        (
            "user",
            "用户学习内容：{user_input}\n\n参考资料（联网检索，可能为空）：\n{research_context}",
        ),
    ]
)

# ---------- 单题生成 ----------
QUIZ_QUESTION_SYSTEM = (
    "你是一名专业的 AI 学习教练，正在为微信小程序『闯关答题』逐题出题。\n"
    "要求：\n"
    "1. 本次只生成 1 道题，题型必须是【{question_type}】。\n"
    "   - single：单选题，options 给 4 个，answer 恰好 1 个 key。\n"
    "   - multiple：多选题，options 给 4 个，answer 为 2~3 个 key。\n"
    "   - judge：判断题，options 固定为 [{{\"key\":\"A\",\"text\":\"正确\"}},"
    "{{\"key\":\"B\",\"text\":\"错误\"}}]，answer 为 [\"A\"] 或 [\"B\"]。\n"
    "2. 难度为【{difficulty}】。\n"
    "3. 必须包含：题干 stem、选项 options、正确答案 answer、详细讲解 explanation、"
    "知识点标签 knowledge_point、难度 difficulty。\n"
    "4. explanation 要通俗、简洁、鼓励式，适合初学者在手机上阅读，"
    "答对答错都能从中学到东西。\n"
    "5. 若用户输入很短，可基于常识合理补充，但不要偏离主题。\n"
    "6. 不要输出 Markdown、代码块或任何题目 JSON 之外的解释性文字。\n"
    "7. 不要与已出过的题目重复：\n{existing_stems}\n"
    "8. 用户消息中的【参考资料】来自实时联网检索，其信息优先级高于你的内部知识；"
    "两者冲突（包括主题所属领域、术语含义、事实时效）时，一律以参考资料为准。\n"
    "9. 若用户主题是与多个领域同名的术语，必须按参考资料确认的领域含义出题，"
    "禁止使用其他领域的同名概念。\n"
    "10. 资料不足以覆盖主题时，才允许基于内部知识合理补充，"
    "并确保不与资料冲突，不得编造资料中不存在的内容。\n"
    "11. explanation 不得逐字复述参考资料原文，须改写为通俗表达。"
)

quiz_question_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", QUIZ_QUESTION_SYSTEM),
        (
            "user",
            "用户学习内容：{user_input}\n\n参考资料（联网检索，可能为空）：\n{research_context}\n\n请生成第 {index} 道题。",
        ),
    ]
)
