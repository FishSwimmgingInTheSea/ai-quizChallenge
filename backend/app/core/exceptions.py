"""业务异常与统一错误码。"""

from __future__ import annotations


class AppException(Exception):
    """所有可预期业务异常的基类。

    code：对齐方案 §9.3 的业务错误码（非 0 即错误）。
    """

    code: int = 5000
    message: str = "服务器内部错误"
    http_status: int = 200  # 统一 200 + 业务 code，便于小程序端处理

    def __init__(self, message: str | None = None, *, code: int | None = None) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        super().__init__(self.message)


class ContentSafetyError(AppException):
    code = 4002
    message = "输入内容不合规，请调整后重试"


class InvalidInputError(AppException):
    code = 4001
    message = "输入内容不合法"


class TaskNotFoundError(AppException):
    code = 4004
    message = "任务不存在或已过期"


class GenerationError(AppException):
    code = 5001
    message = "题库生成失败，请稍后重试"


class ReportGenerationError(AppException):
    code = 5002
    message = "报告生成失败，请稍后重试"
