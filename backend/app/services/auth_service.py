"""登录应用服务：dev 兜底 / 真实 code2session 双模式（用户系统方案设计 §5.2）。

模式判定完全由 settings（WECHAT_APPID + WECHAT_SECRET 是否齐备）驱动，
路由与业务代码不感知差异；测试通过注入 code_exchanger 模拟真实模式。
"""

from __future__ import annotations

from typing import Callable

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import InvalidInputError, WechatLoginError
from app.core.logging import get_logger
from app.core.security import create_token
from app.db.orm_models import DEFAULT_NICKNAME, User
from app.models.user import LoginResult, UserProfile

logger = get_logger(__name__)

# dev 兜底模式的固定开发标识：多次登录必然复用同一账户（需求 §3.2）
DEV_OPENID = "dev_openid_local"

_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"

# code -> openid 的交换器类型（真实实现走 httpx，测试注入假实现）
CodeExchanger = Callable[[str], str]


def _wechat_code2session(settings: Settings, code: str) -> str:
    """真实模式：调用微信 jscode2session 换取 openid（方案 §5.2）。"""
    try:
        resp = httpx.get(
            _CODE2SESSION_URL,
            params={
                "appid": settings.wechat_appid,
                "secret": settings.wechat_secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
            timeout=5.0,
        )
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 - 网络/解析异常统一兜底
        logger.error("code2session 调用失败：%s", exc)
        raise WechatLoginError() from exc
    if data.get("errcode") or not data.get("openid"):
        logger.warning("code2session 返回异常：%s", data)
        raise WechatLoginError()
    return str(data["openid"])


class AuthService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        code_exchanger: CodeExchanger | None = None,
    ) -> None:
        self._db = db
        self._settings = settings or get_settings()
        self._exchange = code_exchanger

    def login(self, code: str) -> LoginResult:
        if not code or not code.strip():
            raise InvalidInputError("缺少登录凭证")

        openid = self._resolve_openid(code.strip())
        user = self._upsert_user(openid)
        token = create_token(user.id)
        return LoginResult(token=token, profile=UserProfile.model_validate(user))

    # ---------- 内部 ----------

    def _resolve_openid(self, code: str) -> str:
        """按配置开关决定真实 / dev 兜底模式（方案 §5.2）。"""
        s = self._settings
        real_mode = bool(s.wechat_appid and s.wechat_secret)
        if not real_mode:
            return DEV_OPENID

        if self._exchange is not None:
            return self._exchange(code)
        return _wechat_code2session(s, code)

    def _upsert_user(self, openid: str) -> User:
        """按 openid 查询 / 建档；并发建档冲突时回查复用。"""
        user = self._db.query(User).filter(User.openid == openid).first()
        if user is not None:
            return user

        user = User(openid=openid, nickname=DEFAULT_NICKNAME, avatar_url="", total_xp=0)
        self._db.add(user)
        try:
            self._db.commit()
        except IntegrityError:
            # 唯一键冲突：另一请求已建档，回查复用
            self._db.rollback()
            user = self._db.query(User).filter(User.openid == openid).first()
            if user is None:
                raise
        # 重新 attach（commit 后默认 expire，这里保持属性可读）
        return user
