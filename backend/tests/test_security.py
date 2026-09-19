"""JWT 工具单元测试（方案 §5.3）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import create_token, decode_token


def test_create_and_decode_roundtrip():
    token = create_token(42)
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert "exp" in payload
    assert "iat" in payload


def test_decode_garbage_token_raises_unauthorized():
    with pytest.raises(UnauthorizedError):
        decode_token("not-a-jwt")


def test_decode_forged_token_raises_unauthorized():
    # 用错误密钥伪造
    forged = pyjwt.encode({"sub": "1"}, "wrong-secret-key-aaaaaaaaaaaaaaaaaaaa", algorithm="HS256")
    with pytest.raises(UnauthorizedError):
        decode_token(forged)


def test_decode_expired_token_raises_unauthorized():
    settings = get_settings()
    expired = pyjwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=10)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError):
        decode_token(expired)


def test_unauthorized_error_maps_to_4010():
    assert UnauthorizedError.code == 4010
    assert UnauthorizedError.http_status == 200
