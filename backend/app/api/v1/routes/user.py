"""用户资料与头像接口（用户系统方案设计 §6 / §8.2）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import get_current_user, get_record_service, get_user_service
from app.api.response import ok
from app.db.orm_models import User
from app.models.user import UpdateProfileRequest
from app.services.record_service import RecordService
from app.services.user_service import UserService

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/profile")
def get_profile(
    user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> dict:
    """获取当前用户资料（必需登录）。"""
    return ok(service.get_profile(user.id).model_dump())


@router.put("/profile")
def update_profile(
    req: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> dict:
    """编辑昵称 / 头像（至少一个字段），返回更新后的完整资料。"""
    return ok(service.update_profile(user.id, req).model_dump())


@router.post("/avatar")
def upload_avatar(
    file: UploadFile = File(..., description="头像文件，jpg/png/webp，≤2MB"),
    user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> dict:
    """上传头像并返回访问路径；不直接绑定资料（方案 §6.3 两步分离）。"""
    content = file.file.read()
    result = service.upload_avatar(user.id, file.filename or "", content)
    return ok(result.model_dump())


@router.get("/stats")
def get_stats(
    user: User = Depends(get_current_user),
    service: RecordService = Depends(get_record_service),
) -> dict:
    """基础统计：闯关次数 / 平均正确率 / 累计 XP（方案 §8.2）。"""
    return ok(service.get_stats(user.id).model_dump())
