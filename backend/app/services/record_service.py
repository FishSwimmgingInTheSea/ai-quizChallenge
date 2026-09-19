"""闯关结算与历史统计应用服务（用户系统方案设计 §7 / §8）。

- 复算：复用 scoring_service，忽略前端上报的 is_correct（§7.3）。
- 事务：INSERT 记录 + 原子加 XP 同一事务，任一失败整体回滚（§7.4）。
- 幂等：client_record_id 唯一索引，冲突时回查返回首次结果（§7.5）。
- 查询：历史倒序分页（§8.1）与基础统计（§8.2），均强制限定当前用户（§12.3）。
"""

from __future__ import annotations

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidInputError
from app.core.logging import get_logger
from app.db.orm_models import QuizQuestionRecord, QuizRecord, QuizReport, User
from app.models.report import Report
from app.models.user import (
    QuizRecordItem,
    QuizRecordsPage,
    RecordDetail,
    RecordQuestionItem,
    RecordSubmitRequest,
    RecordSubmitResult,
    UserStats,
)
from app.services.scoring_service import compute_score_summary, judge_answer

logger = get_logger(__name__)

# 对齐前端 XP_PER_CORRECT = 10（方案 §7.3：用户体感不变）
XP_PER_CORRECT = 10


class RecordService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def submit(self, user_id: int, req: RecordSubmitRequest) -> RecordSubmitResult:
        client_record_id = req.client_record_id.strip()
        title = req.title.strip()
        if not client_record_id:
            raise InvalidInputError("client_record_id 不能为空")
        if not title:
            raise InvalidInputError("标题不能为空")
        if not req.questions:
            raise InvalidInputError("题库为空，无法结算")

        # 服务端权威复算（§7.3：口径与前端一致，但以服务端为准）
        summary = compute_score_summary(req.questions, req.answer_records)
        correct_count = summary["correct_count"]
        accuracy = summary["accuracy"]
        xp_earned = correct_count * XP_PER_CORRECT
        stars = max(1, round(accuracy / 100 * 5))

        record = QuizRecord(
            user_id=user_id,
            client_record_id=client_record_id,
            title=title,
            question_count=len(req.questions),
            correct_count=correct_count,
            accuracy=accuracy,
            duration_ms=max(0, req.duration_ms),
            xp_earned=xp_earned,
            stars=stars,
        )
        self._db.add(record)
        try:
            # flush 拿到 record.id 供明细/报告外键使用；
            # client_record_id 唯一键冲突在此抛出，与 XP 冲突一样走幂等分支
            self._db.flush()
            answers_by_id = {a.question_id: a for a in req.answer_records}
            for index, question in enumerate(req.questions):
                answer = answers_by_id.get(question.id)
                selected = answer.selected_answers if answer else []
                self._db.add(
                    QuizQuestionRecord(
                        record_id=record.id,
                        question_index=index,
                        question_id=question.id,
                        qtype=question.type,
                        difficulty=question.difficulty,
                        knowledge_point=question.knowledge_point,
                        stem=question.stem,
                        explanation=question.explanation,
                        options=[o.model_dump() for o in question.options],
                        answer=question.answer,
                        selected_answers=selected,
                        # 服务端复算口径（§7.3），忽略前端上报的 is_correct
                        is_correct=judge_answer(question, selected),
                        duration_ms=max(0, answer.duration_ms) if answer else 0,
                    )
                )
            if req.report is not None:
                self._db.add(
                    QuizReport(
                        record_id=record.id,
                        user_id=user_id,
                        # 复算值覆盖，与 report_service 口径一致
                        accuracy=accuracy,
                        mastered_points=req.report.mastered_points,
                        weak_points=req.report.weak_points,
                        three_line_summary=req.report.three_line_summary,
                        advice=req.report.advice,
                        share_quote=req.report.share_quote,
                    )
                )
            # 原子加：读出再写回会在多端并发结算时丢更新（§7.4）；
            # execute 的 autoflush 会先冲刷上面的明细/报告 INSERT
            self._db.execute(
                update(User)
                .where(User.id == user_id)
                .values(total_xp=User.total_xp + xp_earned)
            )
            self._db.commit()
        except IntegrityError:
            # 幂等键冲突：回查首次写入结果（§7.5），明细/报告随首次写入已存在
            self._db.rollback()
            return self._replay_result(user_id, client_record_id)

        total_xp = self._current_xp(user_id)
        logger.info(
            "用户 %s 结算 %s...：%d/%d 对，+%d XP",
            user_id, client_record_id[:8], correct_count, len(req.questions), xp_earned,
        )
        return RecordSubmitResult(
            record_id=record.id,
            correct_count=correct_count,
            accuracy=accuracy,
            stars=stars,
            xp_earned=xp_earned,
            total_xp=total_xp,
            duplicated=False,
        )

    # ---------- 查询（§8） ----------

    def list_records(
        self, user_id: int, limit: int = 10, offset: int = 0
    ) -> QuizRecordsPage:
        """当前用户的历史记录，created_at 倒序（同秒时 id 兜底排序）。"""
        base = (
            self._db.query(QuizRecord)
            .filter(QuizRecord.user_id == user_id)
            .order_by(QuizRecord.created_at.desc(), QuizRecord.id.desc())
        )
        total = base.count()
        records = base.limit(limit).offset(offset).all()
        return QuizRecordsPage(
            total=total,
            records=[self._to_item(r) for r in records],
        )

    def get_stats(self, user_id: int) -> UserStats:
        """次数 / 平均正确率 / 累计 XP；total_xp 取 users 权威值（§8.2）。"""
        row = (
            self._db.query(func.count(QuizRecord.id), func.avg(QuizRecord.accuracy))
            .filter(QuizRecord.user_id == user_id)
            .one()
        )
        total_count = int(row[0] or 0)
        avg_accuracy = int(round(row[1])) if row[1] is not None else 0
        user = self._db.get(User, user_id)
        return UserStats(
            total_count=total_count,
            avg_accuracy=avg_accuracy,
            total_xp=user.total_xp if user else 0,
        )

    def get_record_detail(self, user_id: int, record_id: int) -> RecordDetail:
        """单局详情：汇总 + 逐题明细（按 question_index 升序）+ 报告。

        不存在与非本人统一报“记录不存在”，不暴露他人记录存在性（§12.3）。
        """
        record = (
            self._db.query(QuizRecord)
            .filter(QuizRecord.id == record_id, QuizRecord.user_id == user_id)
            .first()
        )
        if record is None:
            raise InvalidInputError("记录不存在")
        items = (
            self._db.query(QuizQuestionRecord)
            .filter(QuizQuestionRecord.record_id == record.id)
            .order_by(QuizQuestionRecord.question_index.asc())
            .all()
        )
        report = (
            self._db.query(QuizReport)
            .filter(QuizReport.record_id == record.id)
            .first()
        )
        return RecordDetail(
            record=self._to_item(record),
            questions=[self._to_question_item(it) for it in items],
            report=self._to_report(report) if report else None,
        )

    @staticmethod
    def _to_item(r: QuizRecord) -> QuizRecordItem:
        return QuizRecordItem(
            record_id=r.id,
            title=r.title,
            question_count=r.question_count,
            correct_count=r.correct_count,
            accuracy=r.accuracy,
            stars=r.stars,
            xp_earned=r.xp_earned,
            duration_ms=r.duration_ms,
            created_at=r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        )

    @staticmethod
    def _to_question_item(it: QuizQuestionRecord) -> RecordQuestionItem:
        return RecordQuestionItem(
            question_index=it.question_index,
            question_id=it.question_id,
            type=it.qtype,
            difficulty=it.difficulty,
            knowledge_point=it.knowledge_point,
            stem=it.stem,
            options=it.options,
            answer=it.answer,
            explanation=it.explanation,
            selected_answers=it.selected_answers,
            is_correct=it.is_correct,
            duration_ms=it.duration_ms,
        )

    @staticmethod
    def _to_report(r: QuizReport) -> Report:
        return Report(
            accuracy=r.accuracy,
            mastered_points=r.mastered_points,
            weak_points=r.weak_points,
            three_line_summary=r.three_line_summary,
            advice=r.advice,
            share_quote=r.share_quote,
        )

    # ---------- 内部 ----------

    def _replay_result(self, user_id: int, client_record_id: str) -> RecordSubmitResult:
        record = (
            self._db.query(QuizRecord)
            .filter(QuizRecord.client_record_id == client_record_id)
            .first()
        )
        if record is None:
            # 理论不可达（唯一索引冲突必已存在）；防御性兜底
            raise InvalidInputError("结算冲突，请重试")
        logger.info("用户 %s 幂等重放：%s...", user_id, client_record_id[:8])
        return RecordSubmitResult(
            record_id=record.id,
            correct_count=record.correct_count,
            accuracy=record.accuracy,
            stars=record.stars,
            xp_earned=record.xp_earned,
            total_xp=self._current_xp(user_id),
            duplicated=True,
        )

    def _current_xp(self, user_id: int) -> int:
        user = self._db.get(User, user_id)
        if user is None:
            raise InvalidInputError("用户不存在")
        # execute(update) 不会同步 session 已加载对象，refresh 强制重读
        self._db.refresh(user)
        return user.total_xp
