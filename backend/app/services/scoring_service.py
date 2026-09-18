"""评分与统计（纯函数，方案 §4.4 流程三第 2 步）。

前端本地判题，但后端在生成报告时仍独立复算一遍统计，保证报告数据真实可信。
"""

from __future__ import annotations

from app.models.quiz import AnswerRecord, Question


def judge_answer(question: Question, selected: list[str]) -> bool:
    """集合完全相等才算正确（单选/多选/判断统一规则，对齐前端）。"""
    return set(question.answer) == set(selected or [])


def compute_score_summary(
    questions: list[Question], records: list[AnswerRecord]
) -> dict:
    """基于题库与作答记录复算统计结果。

    以后端 judge_answer 为准复核 is_correct，避免前端数据被篡改。
    """
    total = len(questions)
    q_by_id = {q.id: q for q in questions}

    correct_count = 0
    mastered: list[str] = []
    weak: list[str] = []
    seen_correct_kp: set[str] = set()
    seen_weak_kp: set[str] = set()

    for record in records:
        question = q_by_id.get(record.question_id)
        if question is None:
            continue
        is_correct = judge_answer(question, record.selected_answers)
        kp = question.knowledge_point
        if is_correct:
            correct_count += 1
            if kp and kp not in seen_correct_kp:
                seen_correct_kp.add(kp)
                mastered.append(kp)
        else:
            if kp and kp not in seen_weak_kp:
                seen_weak_kp.add(kp)
                weak.append(kp)

    accuracy = round(correct_count / total * 100) if total else 0
    # 答对过的知识点若同时出现在薄弱里，以薄弱为准（更利于复习提醒）
    mastered = [kp for kp in mastered if kp not in seen_weak_kp]

    return {
        "total": total,
        "correct_count": correct_count,
        "accuracy": accuracy,
        "mastered_points": mastered,
        "weak_points": weak,
    }
