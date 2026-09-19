"""JWT 签发与校验（用户系统方案设计 §5.3）。

Payload 仅含 sub/iat/exp，不放昵称、头像、openid 等业务字段。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

_ALGORITHM = "HS256"


def create_token(user_id: int) -> str:
    """为指定用户签发 Bearer Token。"""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_expire_days),
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    """校验并解码 Token；任何非法 / 过期情况统一抛 UnauthorizedError(4010)。"""
    settings = get_settings()
    try:
        return pyjwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
    except pyjwt.InvalidTokenError:
        raise UnauthorizedError() from None
