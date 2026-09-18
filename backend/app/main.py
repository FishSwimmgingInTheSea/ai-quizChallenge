"""FastAPI 应用入口：注册路由、异常处理、CORS。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.response import fail
from app.api.v1.routes import health, quiz, report
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging import setup_logging


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()

    app = FastAPI(title="智趣 AI 闯关学习小程序 · 后端", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------- 统一异常处理（始终 200 + 业务 code，方案 §9.3） ----------
    @app.exception_handler(AppException)
    async def _app_exc_handler(_: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=fail(exc.code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=200,
            content=fail(4001, "请求参数不合法", data=exc.errors()),
        )

    @app.exception_handler(Exception)
    async def _fallback_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=200,
            content=fail(5000, "服务器内部错误"),
        )

    api_prefix = "/api/v1"
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(quiz.router, prefix=api_prefix)
    app.include_router(report.router, prefix=api_prefix)

    return app


app = create_app()
