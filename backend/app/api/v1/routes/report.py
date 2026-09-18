"""复盘报告接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_report_service
from app.api.response import ok
from app.models.report import GenerateReportRequest
from app.services.report_service import ReportService

router = APIRouter(prefix="/report", tags=["report"])


@router.post("/generate")
async def generate_report(
    req: GenerateReportRequest,
    service: ReportService = Depends(get_report_service),
) -> dict:
    report = await service.generate(req)
    return ok(report.model_dump())
