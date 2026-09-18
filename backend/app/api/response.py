"""统一响应封装（方案 §9.3）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any = None


def ok(data: Any = None, message: str = "ok") -> dict:
    return ApiResponse(code=0, message=message, data=data).model_dump()


def fail(code: int, message: str, data: Any = None) -> dict:
    return ApiResponse(code=code, message=message, data=data).model_dump()
