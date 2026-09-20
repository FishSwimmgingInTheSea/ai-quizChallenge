"""ORM 模型：users / quiz_records（用户系统方案设计 §4.2 / §4.3）。

与已初始化的 MySQL 表结构一一对应；类型用 with_variant 保持
MySQL 无符号精度，同时兼容 SQLite 测试库（方案 §4.5）。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DEFAULT_NICKNAME = "学习小达人"


def _bigint_pk() -> Mapped[int]:
    """主键：MySQL 下 BIGINT UNSIGNED；SQLite 下 INTEGER（才能自动生成 rowid）。"""
    return mapped_column(
        Integer().with_variant(mysql.BIGINT(unsigned=True), "mysql"),
        primary_key=True,
        autoincrement=True,
    )


def _small_unsigned():
    """SMALLINT UNSIGNED（SQLite 退化为 SMALLINT）。"""
    return SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = _bigint_pk()
    openid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    nickname: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DEFAULT_NICKNAME
    )
    avatar_url: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # 累计经验值：服务端权威，只允许原子加（方案 §7.4）
    total_xp: Mapped[int] = mapped_column(
        Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
        nullable=False,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class QuizRecord(Base):
    __tablename__ = "quiz_records"
    __table_args__ = (
        Index("idx_records_user_time", "user_id", "created_at"),
    )

    id: Mapped[int] = _bigint_pk()
    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql"),
        ForeignKey("users.id"),
        nullable=False,
    )
    # 幂等键：前端每局生成的唯一 ID（方案 §7.5）
    client_record_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)

    question_count: Mapped[int] = mapped_column(_small_unsigned(), nullable=False)
    correct_count: Mapped[int] = mapped_column(_small_unsigned(), nullable=False)
    # 正确率 0-100，服务端复算后写入
    accuracy: Mapped[int] = mapped_column(_small_unsigned(), nullable=False)
    duration_ms: Mapped[int] = mapped_column(
        Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
        nullable=False,
        default=0,
    )
    xp_earned: Mapped[int] = mapped_column(_small_unsigned(), nullable=False)
    stars: Mapped[int] = mapped_column(
        SmallInteger().with_variant(mysql.TINYINT(unsigned=True), "mysql"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), server_default=func.now(), nullable=False
    )


class QuizQuestionRecord(Base):
    """题目记录表：每局每题一行，自包含题快照 + 作答（P1 错题本的数据基础）。

    快照全量冗余存储，错题回顾时无需回查任何题库；is_correct 为服务端
    judge_answer 复算值（§7.3），忽略前端上报。
    """

    __tablename__ = "quiz_record_items"
    __table_args__ = (
        Index("idx_items_record", "record_id"),
    )

    id: Mapped[int] = _bigint_pk()
    record_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql"),
        ForeignKey("quiz_records.id"),
        nullable=False,
    )
    # 0-based，与提交时 questions 数组顺序一致
    question_index: Mapped[int] = mapped_column(_small_unsigned(), nullable=False)
    question_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # ---- 题快照 ----
    qtype: Mapped[str] = mapped_column(String(16), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    knowledge_point: Mapped[str] = mapped_column(String(100), nullable=False)
    stem: Mapped[str] = mapped_column(Text(), nullable=False)
    explanation: Mapped[str] = mapped_column(Text(), nullable=False)
    # 配图永久 URL（question-images）；无图时空串（已有表需手动 ALTER 加列）
    image_url: Mapped[str] = mapped_column(
        String(500), nullable=False, default=""
    )
    # JSON 列：MySQL 原生 JSON，SQLite 退化为 TEXT（读写透明，§4.5 双库约定）
    options: Mapped[list] = mapped_column(JSON(), nullable=False)
    answer: Mapped[list] = mapped_column(JSON(), nullable=False)

    # ---- 作答 ----
    selected_answers: Mapped[list] = mapped_column(JSON(), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean(), nullable=False)
    duration_ms: Mapped[int] = mapped_column(
        Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
        nullable=False,
        default=0,
    )


class QuizReport(Base):
    """报告表：与 quiz_records 一对一，存储用户实际看到的复盘报告。

    accuracy 落库前被服务端复算覆盖（与 report_service 口径一致）。
    """

    __tablename__ = "quiz_reports"
    __table_args__ = (
        Index("idx_reports_user_time", "user_id", "created_at"),
    )

    id: Mapped[int] = _bigint_pk()
    record_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql"),
        ForeignKey("quiz_records.id"),
        unique=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql"),
        ForeignKey("users.id"),
        nullable=False,
    )
    accuracy: Mapped[int] = mapped_column(_small_unsigned(), nullable=False)
    mastered_points: Mapped[list] = mapped_column(JSON(), nullable=False)
    weak_points: Mapped[list] = mapped_column(JSON(), nullable=False)
    three_line_summary: Mapped[list] = mapped_column(JSON(), nullable=False)
    advice: Mapped[list] = mapped_column(JSON(), nullable=False)
    share_quote: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), server_default=func.now(), nullable=False
    )


class KbDocument(Base):
    """知识库文档表：上传记录 + 异步处理状态机 + 向量入库统计。

    status：processing（后台解析/向量化中）→ ready（可检索）/ failed（解析或
    嵌入失败，error 存原因）；向量本体在 Chroma（user_{id} collection，
    doc_id 元数据），MySQL 只存元信息与状态。
    """

    __tablename__ = "kb_documents"
    __table_args__ = (
        Index("idx_kb_docs_user_time", "user_id", "created_at"),
    )

    id: Mapped[int] = _bigint_pk()
    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql"),
        ForeignKey("users.id"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # pdf / docx / md / txt
    doc_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # 上传文件字节数
    file_size: Mapped[int] = mapped_column(
        Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
        nullable=False,
    )
    # 解析后纯文本字符数 / 分块数（ready 后有值）
    char_count: Mapped[int] = mapped_column(
        Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
        nullable=False,
        default=0,
    )
    chunk_count: Mapped[int] = mapped_column(_small_unsigned(), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="processing")
    # 失败原因（截断 255）；成功时空串
    error: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ImageGenUsage(Base):
    """每人每日生图用量计数（question-images D3）。

    按 (user_id, usage_date) 唯一一行，count 为该自然日已生成配图张数；
    跨自然日因 usage_date 不同自动开新行，配额自然恢复。唯一约束 +
    原子自增抵并发超发；跨重启持久（区别于进程内计数）。
    """

    __tablename__ = "image_gen_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "usage_date", name="uq_image_usage_user_date"),
    )

    id: Mapped[int] = _bigint_pk()
    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(mysql.BIGINT(unsigned=True), "mysql"),
        ForeignKey("users.id"),
        nullable=False,
    )
    # 自然日（按服务器本地日期归属配额）
    usage_date: Mapped[date] = mapped_column(Date(), nullable=False)
    count: Mapped[int] = mapped_column(
        Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
        nullable=False,
        default=0,
    )
