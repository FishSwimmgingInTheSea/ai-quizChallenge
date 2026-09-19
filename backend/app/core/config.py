"""应用配置：统一从环境变量 / .env 读取（pydantic-settings）。"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # DeepSeek / OpenAI 兼容
    deepseek_api_key: str = "sk-placeholder"
    deepseek_base_url: str = "https://api.deepseek.com"
    # 官方 2026-07-24 停用 deepseek-chat/deepseek-reasoner，升级为现行轻量主力模型
    deepseek_model: str = "deepseek-flash"
    # 思考模式（deepseek-flash 默认开启；思考模式与结构化输出的强制 tool_choice
    # 互斥，报 400 "Thinking mode does not support this tool_choice"，故默认禁用）
    deepseek_thinking: Literal["disabled", "enabled"] = "disabled"

    # 出题模型参数
    quiz_temperature: float = 0.4
    quiz_top_p: float = 0.9
    quiz_max_tokens: int = 1200
    llm_timeout: int = 30
    llm_max_retries: int = 2

    # 报告模型参数
    report_temperature: float = 0.5

    # ===== 联网研究（quiz-web-search-grounding D9） =====
    # Tavily 密钥；空 = 研究阶段自动降级为纯模型出题
    tavily_api_key: str = ""
    research_enabled: bool = True
    research_max_tool_calls: int = 6
    research_max_model_calls: int = 8
    research_timeout: float = 60
    research_temperature: float = 0.2
    research_results_limit: int = 8
    research_per_source_max_chars: int = 2500
    research_tool_output_max_chars: int = 6000
    research_context_max_chars: int = 6000
    research_cache_ttl_seconds: int = 900

    # 业务参数
    input_min_len: int = 2
    input_max_len: int = 500
    default_question_count: int = 5
    task_ttl_seconds: int = 1800

    # 服务
    cors_allow_origins: str = "*"
    log_level: str = "INFO"

    # ===== 用户系统（用户系统方案设计 §11） =====
    # 未配置 MySQL 时回退本地 SQLite 文件，保证可启动；正式环境必须在 .env 指定 MySQL
    database_url: str = "sqlite:///./ai_quiz_local.db"
    # 任一为空 -> dev 兜底登录（不调 code2session）；两者均配置 -> 真实登录
    wechat_appid: str = ""
    wechat_secret: str = ""
    jwt_secret: str = "dev-insecure-secret-please-change-me-32bytes"
    jwt_expire_days: int = 30
    # 头像上传目录（相对运行目录），对外经 /static 挂载
    upload_dir: str = "uploads"

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_allow_origins.strip()
        if raw == "*" or not raw:
            return ["*"]
        return [item.strip() for item in raw.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    """获取全局单例配置。"""
    return Settings()
