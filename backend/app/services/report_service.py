"""报告应用服务：复算统计 + 调用报告链生成结构化复盘报告。"""

from __future__ import annotations

import json

from app.core.exceptions import ReportGenerationError
from app.core.logging import get_logger
from app.llm.report_chain import LangChainReportGenerator, ReportGenerator
from app.models.report import GenerateReportRequest, Report
from app.services.scoring_service import compute_score_summary

logger = get_logger(__name__)


class ReportService:
    def __init__(self, generator: ReportGenerator | None = None) -> None:
        self._generator = generator or LangChainReportGenerator()

    async def generate(self, req: GenerateReportRequest) -> Report:
        # 后端独立复算统计，报告数据以此为准（不盲信前端/模型）
        summary = compute_score_summary(req.questions, req.answer_records)

        quiz_json = json.dumps(
            [q.model_dump() for q in req.questions], ensure_ascii=False
        )
        records_json = json.dumps(
            [r.model_dump() for r in req.answer_records], ensure_ascii=False
        )
        summary_json = json.dumps(summary, ensure_ascii=False)

        try:
            draft = await self._generator.generate(
                topic=req.topic,
                quiz_json=quiz_json,
                answer_records=records_json,
                score_summary=summary_json,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("报告生成失败：%s", exc)
            raise ReportGenerationError() from exc

        # 用后端复算的正确率覆盖模型输出，保证真实
        return Report(
            accuracy=summary["accuracy"],
            mastered_points=draft.mastered_points or summary["mastered_points"],
            weak_points=draft.weak_points or summary["weak_points"],
            three_line_summary=draft.three_line_summary,
            advice=draft.advice,
            share_quote=draft.share_quote,
        )
