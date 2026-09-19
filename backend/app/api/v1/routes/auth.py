"""登录接口（用户系统方案设计 §5.1）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_auth_service
from app.api.response import ok
from app.models.user import LoginRequest
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(
    req: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> dict:
    """微信一键登录：wx.login code 换 Token（dev 兜底 / 真实模式由配置决定）。"""
    result = service.login(req.code)
    return ok(result.model_dump())
