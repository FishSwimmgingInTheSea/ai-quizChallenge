"""健康检查接口。"""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.api.response import ok

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return ok({"status": "up", "version": __version__})
