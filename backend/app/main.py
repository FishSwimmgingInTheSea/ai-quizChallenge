"""FastAPI 应用入口：注册路由、异常处理、CORS、数据库生命周期。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.response import fail
from app.api.v1.routes import auth, health, kb, meta, quiz, report, user
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging import setup_logging
from app.db.session import dispose_engine, init_db


@asynccontextmanager
async def _lifespan(_: FastAPI):
    # 启动：幂等建表；关闭：释放连接池（用户系统方案设计 §4.1 运行时约定）
    init_db()
    yield
    dispose_engine()


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()

    app = FastAPI(
        title="智趣 AI 闯关学习小程序 · 后端",
        version="0.1.0",
        lifespan=_lifespan,
    )

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
        # 自定义校验器的 ctx 含异常对象不可 JSON 序列化，回包剔除（msg 已含原因）
        errors = [{k: v for k, v in err.items() if k != "ctx"} for err in exc.errors()]
        return JSONResponse(
            status_code=200,
            content=fail(4001, "请求参数不合法", data=errors),
        )

    @app.exception_handler(Exception)
    async def _fallback_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=200,
            content=fail(5000, "服务器内部错误"),
        )

    api_prefix = "/api/v1"
    app.include_router(health.router, prefix=api_prefix)
    app.include_router(meta.router, prefix=api_prefix)
    app.include_router(quiz.router, prefix=api_prefix)
    app.include_router(report.router, prefix=api_prefix)
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(user.router, prefix=api_prefix)
    app.include_router(kb.router, prefix=api_prefix)

    # 头像等静态资源：uploads/ 挂到 /static（用户系统方案设计 §6.3）
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(upload_dir)), name="static")

    return app


app = create_app()
