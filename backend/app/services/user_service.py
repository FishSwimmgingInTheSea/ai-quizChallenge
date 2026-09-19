"""用户资料与头像应用服务（用户系统方案设计 §6）。

- 昵称：strip 后 1~16 字符，敏感词校验复用 content_filter（4002）。
- avatar_url：仅允许本服务 /static/avatars/{user_id}/ 前缀，防外链与越权引用。
- 头像上传：两步分离——本服务只落盘返回 URL，不写库；绑定由 PUT /user/profile 完成。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ContentSafetyError, InvalidInputError
from app.core.logging import get_logger
from app.db.orm_models import User
from app.models.user import AvatarUploadResult, UpdateProfileRequest, UserProfile
from app.utils.content_filter import contains_sensitive

logger = get_logger(__name__)

NICKNAME_MAX_LEN = 16
MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 方案 §6.3
ALLOWED_AVATAR_EXTS = {"jpg", "jpeg", "png", "webp"}
_STATIC_PREFIX = "/static/avatars"


class UserService:
    def __init__(self, db: Session, *, settings: Settings | None = None) -> None:
        self._db = db
        self._settings = settings or get_settings()

    def get_profile(self, user_id: int) -> UserProfile:
        return UserProfile.model_validate(self._require_user(user_id))

    def update_profile(
        self, user_id: int, req: UpdateProfileRequest
    ) -> UserProfile:
        user = self._require_user(user_id)

        if req.nickname is None and req.avatar_url is None:
            raise InvalidInputError("至少传入一个待更新字段")

        if req.nickname is not None:
            user.nickname = self._clean_nickname(req.nickname)
        if req.avatar_url is not None:
            user.avatar_url = self._clean_avatar_url(user_id, req.avatar_url)

        self._db.commit()
        logger.info("用户 %s 更新资料：nickname=%s", user_id, req.nickname is not None)
        return UserProfile.model_validate(user)

    def upload_avatar(
        self, user_id: int, filename: str, content: bytes
    ) -> AvatarUploadResult:
        """校验并落盘头像文件，返回访问 URL；不写库（方案 §6.3 两步分离）。"""
        self._require_user(user_id)

        ext = Path(filename).suffix.lower().lstrip(".")
        if ext not in ALLOWED_AVATAR_EXTS:
            raise InvalidInputError("头像仅支持 jpg / png / webp 格式")
        if len(content) > MAX_AVATAR_BYTES:
            raise InvalidInputError("头像大小不能超过 2MB")
        if not content:
            raise InvalidInputError("头像文件内容为空")

        rel_dir = Path("avatars") / str(user_id)
        abs_dir = Path(self._settings.upload_dir) / rel_dir
        abs_dir.mkdir(parents=True, exist_ok=True)

        name = f"{uuid4().hex}.{ext}"
        (abs_dir / name).write_bytes(content)

        url = f"{_STATIC_PREFIX}/{user_id}/{name}"
        logger.info("用户 %s 上传头像：%s（%d 字节）", user_id, name, len(content))
        return AvatarUploadResult(avatar_url=url)

    # ---------- 内部 ----------

    def _require_user(self, user_id: int) -> User:
        user = self._db.get(User, user_id)
        if user is None:
            # Token 合法但用户已被删：按未登录处理
            from app.core.exceptions import UnauthorizedError

            raise UnauthorizedError()
        return user

    @staticmethod
    def _clean_nickname(raw: str) -> str:
        nickname = (raw or "").strip()
        if not nickname:
            raise InvalidInputError("昵称不能为空")
        if len(nickname) > NICKNAME_MAX_LEN:
            raise InvalidInputError(f"昵称长度不能超过 {NICKNAME_MAX_LEN} 个字符")
        if contains_sensitive(nickname):
            raise ContentSafetyError("昵称包含不合规内容，请调整后重试")
        return nickname

    @staticmethod
    def _clean_avatar_url(user_id: int, url: str) -> str:
        prefix = f"{_STATIC_PREFIX}/{user_id}/"
        if not url.startswith(prefix) or ".." in url:
            raise InvalidInputError("头像地址不合法，请先通过上传接口获取")
        return url
