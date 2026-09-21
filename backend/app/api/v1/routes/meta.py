"""元信息接口：功能标志暴露给前端控制入口渲染（如首页配图开关）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_image_service
from app.api.response import ok
from app.services.image_service import ImageService

router = APIRouter(tags=["meta"])


@router.get("/meta/features")
async def features(service: ImageService = Depends(get_image_service)) -> dict:
    """功能标志（公开免登录）：image_gen_enabled 为系统级有效值
    （总开关 + 百炼密钥 + COS 凭据），前端为 false 时隐藏配图入口。"""
    return ok({"image_gen_enabled": service.system_available()})
