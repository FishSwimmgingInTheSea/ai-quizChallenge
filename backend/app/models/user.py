"""用户系统 DTO（用户系统方案设计 §6 / §7 / §9）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.quiz import AnswerRecord, Option, Question
from app.models.report import Report


class LoginRequest(BaseModel):
    code: str = Field(description="wx.login 获取的临时凭证；dev 模式下值被忽略")


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nickname: str
    avatar_url: str
    total_xp: int


class LoginResult(BaseModel):
    token: str
    profile: UserProfile


class UpdateProfileRequest(BaseModel):
    """编辑资料：两字段均可选，至少传一个（服务层校验，方案 §6.2）。"""

    nickname: str | None = Field(
        default=None, description="新昵称；1~16 个字符，去除首尾空白"
    )
    avatar_url: str | None = Field(
        default=None, description="新头像地址；仅允许本服务 /static/avatars/ 前缀"
    )


class AvatarUploadResult(BaseModel):
    avatar_url: str = Field(description="上传后的头像访问路径，如 /static/avatars/12/a1b2.jpg")


class RecordSubmitRequest(BaseModel):
    """通关结算入参（方案 §7.2）：完整题库 + 作答，服务端复算权威成绩。"""

    client_record_id: str = Field(min_length=1, max_length=64, description="前端每局生成的唯一幂等键")
    title: str = Field(min_length=1, max_length=100, description="闯关标题")
    duration_ms: int = Field(default=0, ge=0, description="整局用时（毫秒）")
    questions: list[Question]
    answer_records: list[AnswerRecord]
    report: Report | None = Field(
        default=None, description="用户实际看到的复盘报告；缺省则不写报告行（兼容旧客户端）"
    )


class RecordSubmitResult(BaseModel):
    record_id: int
    correct_count: int
    accuracy: int
    stars: int
    xp_earned: int
    total_xp: int = Field(description="累加后的用户权威总 XP")
    duplicated: bool = Field(description="true 表示幂等重放，未重复加 XP")


class QuizRecordItem(BaseModel):
    """历史记录条目（方案 §8.1）。"""

    record_id: int
    title: str
    question_count: int
    correct_count: int
    accuracy: int
    stars: int
    xp_earned: int
    duration_ms: int
    created_at: str


class QuizRecordsPage(BaseModel):
    total: int
    records: list[QuizRecordItem]


class RecordQuestionItem(BaseModel):
    """单题明细：自包含题快照 + 作答；is_correct 为服务端复算值。"""

    question_index: int
    question_id: str
    type: str
    difficulty: str
    knowledge_point: str
    stem: str
    options: list[Option]
    answer: list[str]
    explanation: str
    selected_answers: list[str]
    is_correct: bool
    duration_ms: int
    # 题目当时保存的配图永久 URL（question-images）；无图时空串
    image_url: str = ""


class RecordDetail(BaseModel):
    """单局记录详情：汇总 + 逐题明细 + 复盘报告（未存报告时为 null）。"""

    record: QuizRecordItem
    questions: list[RecordQuestionItem]
    report: Report | None


class UserStats(BaseModel):
    """基础统计（方案 §8.2）。"""

    total_count: int
    avg_accuracy: int
    total_xp: int
