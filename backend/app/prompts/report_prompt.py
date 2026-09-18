"""复盘报告 Prompt（版本化，方案 §8.5/§8.6）。"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

REPORT_PROMPT_VERSION = "report_prompt_v1"

REPORT_SYSTEM = (
    "你是一名学习复盘教练，请根据用户本次闯关答题记录生成一份结构化复盘报告。\n"
    "要求：\n"
    "1. 语言清晰、鼓励式，但不空泛，要基于用户真实答题情况，不要编造未出现的结论。\n"
    "2. mastered_points 为掌握较好的知识点，weak_points 为薄弱知识点。\n"
    "3. three_line_summary 恰好三句知识总结，advice 为 1~3 条后续建议。\n"
    "4. share_quote 是一句可用于分享海报的学习金句，简短有力。\n"
    "5. 总结适合移动端阅读，不要输出 JSON 之外的内容。"
)

report_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", REPORT_SYSTEM),
        (
            "user",
            "用户主题：{topic}\n"
            "题库数据：{quiz_json}\n"
            "答题记录：{answer_records}\n"
            "统计结果：{score_summary}",
        ),
    ]
)
