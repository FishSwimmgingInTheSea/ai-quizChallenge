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

    # ===== 知识库 RAG（用户私有知识库） =====
    # 百炼（DashScope）OpenAI 兼容接口；空 = 知识库功能不可用（上传报错/检索降级）
    dashscope_api_key: str = ""
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    # embedding 单请求最大文本条数（百炼 text-embedding-v4 限 10 行/请求）
    embedding_batch_size: int = 10

    # 知识库总开关（紧急关断用）
    kb_enabled: bool = True
    # Chroma 持久化目录（相对运行目录，重启不丢数据）
    kb_persist_dir: str = "kb_data"
    # 文本分块：块大小 / 相邻块重叠（字符数）
    kb_chunk_size: int = 500
    kb_chunk_overlap: int = 50
    # 单文档大小上限（MB）
    kb_max_file_mb: int = 10
    # kb_search 默认/最大检索条数
    kb_top_k: int = 4
    kb_top_k_limit: int = 8

    # ===== 题目 AI 配图（question-images） =====
    # 配图总开关（紧急关断用）；关闭或未配依赖时全链路静默降级为不配图
    image_gen_enabled: bool = False
    # 百炼文生图模型与分辨率（qwen-image-2.0 仅支持同步接口）
    dashscope_image_model: str = "qwen-image-2.0"
    image_size: str = "512*512"
    # 每人每日生图张数上限（DB 持久化按用户按自然日计数）
    image_daily_limit: int = 20
    # 单张生图 + 下载 + 上传的总超时（秒）
    image_gen_timeout: int = 30
    # 生图提示词最大长度（超长截断）
    image_prompt_max_len: int = 300
    # 反向提示词（避免出现文字水印、乱码等）
    image_negative_prompt: str = "文字, 水印, 乱码, 低质量, 模糊"
    # 腾讯云 COS（公有读桶 + 默认域名）；任一为空 = 配图不可用（静默降级）
    cos_secret_id: str = ""
    cos_secret_key: str = ""
    cos_bucket: str = ""
    cos_region: str = ""

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
