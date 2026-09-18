"""应用配置：统一从环境变量 / .env 读取（pydantic-settings）。"""

from __future__ import annotations

from functools import lru_cache

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
    deepseek_model: str = "deepseek-chat"

    # 出题模型参数
    quiz_temperature: float = 0.4
    quiz_top_p: float = 0.9
    quiz_max_tokens: int = 1200
    llm_timeout: int = 30
    llm_max_retries: int = 2

    # 报告模型参数
    report_temperature: float = 0.5

    # 业务参数
    input_min_len: int = 2
    input_max_len: int = 500
    default_question_count: int = 5
    task_ttl_seconds: int = 1800

    # 服务
    cors_allow_origins: str = "*"
    log_level: str = "INFO"

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
