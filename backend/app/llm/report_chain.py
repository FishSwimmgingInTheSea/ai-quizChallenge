"""报告链：封装复盘报告生成，暴露 ReportGenerator 协议。"""

from __future__ import annotations

from typing import Protocol

from app.llm.langchain_factory import get_report_model, with_structured_output
from app.llm.output_schemas import ReportDraft
from app.prompts.report_prompt import report_prompt


class ReportGenerator(Protocol):
    async def generate(
        self,
        topic: str,
        quiz_json: str,
        answer_records: str,
        score_summary: str,
    ) -> ReportDraft: ...


class LangChainReportGenerator:
    def __init__(self) -> None:
        model = get_report_model()
        self._chain = report_prompt | with_structured_output(model, ReportDraft)

    async def generate(
        self,
        topic: str,
        quiz_json: str,
        answer_records: str,
        score_summary: str,
    ) -> ReportDraft:
        return await self._chain.ainvoke(
            {
                "topic": topic,
                "quiz_json": quiz_json,
                "answer_records": answer_records,
                "score_summary": score_summary,
            }
        )
