"""结算写入接口测试（用户系统方案设计 §7：批次三）。

- 服务端复算：忽略前端伪造的 is_correct（方案 §7.3）。
- 幂等：同一 client_record_id 重复提交 duplicated=true 且不重复加 XP（§7.5）。
- 事务：记录写入与 XP 原子累加同生共死（§7.4）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db, get_record_service
from app.core.security import create_token
from app.main import create_app
from app.models.quiz import AnswerRecord, Option, Question
from app.services.record_service import RecordService


def make_questions(n: int = 5) -> list[Question]:
    return [
        Question(
            id=f"q{i}",
            type="single",
            stem=f"第{i}题：哪个说法正确？",
            options=[Option(key="A", text="正确项"), Option(key="B", text="干扰项")],
            answer=["A"],
            explanation="A 是正确项。",
            knowledge_point=f"知识点{i}",
            difficulty="easy",
        )
        for i in range(1, n + 1)
    ]


def make_answers(questions: list[Question], wrong_ids: set[str]) -> list[AnswerRecord]:
    """作答记录：is_correct 一律伪造为 True，正确与否由选项决定，验证服务端复算。"""
    return [
        AnswerRecord(
            question_id=q.id,
            selected_answers=["B"] if q.id in wrong_ids else ["A"],
            is_correct=True,
            duration_ms=1200,
        )
        for q in questions
    ]


@pytest.fixture
def record_client(db_sessionmaker: sessionmaker) -> TestClient:
    app = create_app()

    def override_db():
        session = db_sessionmaker()
        try:
            yield session
        finally:
            session.close()

    def override_record_service():
        return RecordService(db_sessionmaker())

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_record_service] = override_record_service
    return TestClient(app)


@pytest.fixture
def user_id(db_sessionmaker: sessionmaker) -> int:
    from app.db.orm_models import User

    with db_sessionmaker() as session:
        user = User(openid="openid-record-test")
        session.add(user)
        session.commit()
        return user.id


def auth_header(uid: int) -> dict:
    return {"Authorization": f"Bearer {create_token(uid)}"}


def submit(
    client: TestClient,
    uid: int,
    questions: list[Question],
    answers: list[AnswerRecord],
    *,
    client_record_id: str = "cr-1",
    title: str = "测试闯关",
    report: dict | None = None,
) -> dict:
    payload: dict = {
        "client_record_id": client_record_id,
        "title": title,
        "duration_ms": 152000,
        "questions": [q.model_dump() for q in questions],
        "answer_records": [a.model_dump() for a in answers],
    }
    if report is not None:
        payload["report"] = report
    resp = client.post(
        "/api/v1/quiz/records",
        json=payload,
        headers=auth_header(uid),
    )
    assert resp.status_code == 200
    return resp.json()


def make_report_payload(accuracy: int = 99) -> dict:
    """报告载荷；accuracy 默认伪造成 99，验证落库时被服务端复算覆盖。"""
    return {
        "accuracy": accuracy,
        "mastered_points": ["知识点1"],
        "weak_points": ["知识点2"],
        "three_line_summary": ["第一句", "第二句", "第三句"],
        "advice": ["多复习"],
        "share_quote": "温故而知新",
    }


# ---------- 基础与鉴权 ----------


def test_submit_requires_login(record_client: TestClient):
    resp = record_client.post(
        "/api/v1/quiz/records",
        json={"client_record_id": "cr", "title": "t", "duration_ms": 1, "questions": [], "answer_records": []},
    )
    assert resp.json()["code"] == 4010


def test_submit_empty_questions_returns_4001(
    record_client: TestClient, user_id: int
):
    resp = record_client.post(
        "/api/v1/quiz/records",
        json={
            "client_record_id": "cr-empty",
            "title": "空题库",
            "duration_ms": 1,
            "questions": [],
            "answer_records": [],
        },
        headers=auth_header(user_id),
    )
    assert resp.json()["code"] == 4001


def test_submit_blank_client_record_id_returns_4001(
    record_client: TestClient, user_id: int
):
    questions = make_questions(1)
    answers = make_answers(questions, set())
    resp = record_client.post(
        "/api/v1/quiz/records",
        json={
            "client_record_id": "   ",
            "title": "空白幂等键",
            "duration_ms": 1,
            "questions": [q.model_dump() for q in questions],
            "answer_records": [a.model_dump() for a in answers],
        },
        headers=auth_header(user_id),
    )
    assert resp.json()["code"] == 4001


def test_submit_blank_title_returns_4001(record_client: TestClient, user_id: int):
    questions = make_questions(1)
    answers = make_answers(questions, set())
    resp = record_client.post(
        "/api/v1/quiz/records",
        json={
            "client_record_id": "cr-no-title",
            "title": "   ",
            "duration_ms": 1,
            "questions": [q.model_dump() for q in questions],
            "answer_records": [a.model_dump() for a in answers],
        },
        headers=auth_header(user_id),
    )
    assert resp.json()["code"] == 4001


# ---------- 复算与 XP ----------


def test_submit_recomputes_and_ignores_forged_is_correct(
    record_client: TestClient, user_id: int, db_sessionmaker: sessionmaker
):
    questions = make_questions(5)
    # q2 实际选错，但 is_correct 伪造为 true：服务端必须按复算 4 对
    answers = make_answers(questions, {"q2"})

    body = submit(record_client, user_id, questions, answers)
    assert body["code"] == 0
    data = body["data"]
    assert data["correct_count"] == 4
    assert data["accuracy"] == 80
    assert data["stars"] == 4
    assert data["xp_earned"] == 40
    assert data["duplicated"] is False
    assert data["total_xp"] == 40

    from app.db.orm_models import QuizRecord, User

    with db_sessionmaker() as session:
        record = session.query(QuizRecord).one()
        assert record.correct_count == 4
        assert record.question_count == 5
        assert session.get(User, user_id).total_xp == 40


def test_submit_all_wrong_stars_floor_one(
    record_client: TestClient, user_id: int
):
    questions = make_questions(5)
    answers = make_answers(questions, {q.id for q in questions})

    body = submit(record_client, user_id, questions, answers)
    data = body["data"]
    assert data["correct_count"] == 0
    assert data["accuracy"] == 0
    assert data["stars"] == 1  # 星级下限 1（方案 §7.3）
    assert data["xp_earned"] == 0
    assert data["total_xp"] == 0


def test_submit_two_rounds_accumulate_xp(
    record_client: TestClient, user_id: int, db_sessionmaker: sessionmaker
):
    q1 = make_questions(5)
    submit(record_client, user_id, q1, make_answers(q1, {"q2"}), client_record_id="r1")

    q2 = make_questions(5)
    body2 = submit(
        record_client, user_id, q2, make_answers(q2, {"q2", "q3"}), client_record_id="r2"
    )
    assert body2["data"]["total_xp"] == 40 + 30

    from app.db.orm_models import QuizRecord

    with db_sessionmaker() as session:
        assert session.query(QuizRecord).count() == 2


# ---------- 幂等 ----------


def test_submit_same_client_record_id_is_idempotent(
    record_client: TestClient, user_id: int, db_sessionmaker: sessionmaker
):
    questions = make_questions(5)
    first = submit(
        record_client, user_id, questions, make_answers(questions, {"q2"}),
        client_record_id="dup-key",
    )

    # 第二次提交（数据可不同，幂等键相同即视为重放）
    replay = submit(
        record_client, user_id, questions, make_answers(questions, set()),
        client_record_id="dup-key",
    )
    assert replay["code"] == 0
    assert replay["data"]["duplicated"] is True
    assert replay["data"]["record_id"] == first["data"]["record_id"]
    # 返回首次写入的结果口径，且 XP 未重复累加
    assert replay["data"]["xp_earned"] == first["data"]["xp_earned"]
    assert replay["data"]["total_xp"] == first["data"]["total_xp"]

    from app.db.orm_models import QuizRecord, User

    with db_sessionmaker() as session:
        assert session.query(QuizRecord).count() == 1
        assert session.get(User, user_id).total_xp == first["data"]["total_xp"]


# ---------- 历史列表（方案 §8.1） ----------


def _seed_rounds(client: TestClient, uid: int, count: int = 3) -> None:
    """连续结算 count 局，第 i 局答对 i 题。"""
    for i in range(1, count + 1):
        questions = make_questions(5)
        wrong = {q.id for q in questions[i:]}
        submit(
            client, uid, questions, make_answers(questions, wrong),
            client_record_id=f"hist-{i}", title=f"第{i}局",
        )


def test_list_records_requires_login(record_client: TestClient):
    resp = record_client.get("/api/v1/quiz/records")
    assert resp.json()["code"] == 4010


def test_list_records_empty(record_client: TestClient, user_id: int):
    resp = record_client.get(
        "/api/v1/quiz/records", headers=auth_header(user_id)
    )
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {"total": 0, "records": []}


def test_list_records_desc_and_pagination(
    record_client: TestClient, user_id: int
):
    _seed_rounds(record_client, user_id, count=3)

    # 第一页：limit=2，倒序（最新在前）
    resp = record_client.get(
        "/api/v1/quiz/records?limit=2&offset=0",
        headers=auth_header(user_id),
    )
    body = resp.json()["data"]
    assert body["total"] == 3
    assert [r["title"] for r in body["records"]] == ["第3局", "第2局"]

    first = body["records"][0]
    assert first["question_count"] == 5
    assert first["correct_count"] == 3
    assert first["accuracy"] == 60
    assert first["stars"] == 3
    assert first["xp_earned"] == 30
    assert "created_at" in first

    # 第二页
    resp2 = record_client.get(
        "/api/v1/quiz/records?limit=2&offset=2",
        headers=auth_header(user_id),
    )
    body2 = resp2.json()["data"]
    assert body2["total"] == 3
    assert [r["title"] for r in body2["records"]] == ["第1局"]


def test_list_records_limit_over_max_returns_4001(
    record_client: TestClient, user_id: int
):
    resp = record_client.get(
        "/api/v1/quiz/records?limit=999",
        headers=auth_header(user_id),
    )
    assert resp.json()["code"] == 4001


def test_list_records_only_returns_own_records(
    record_client: TestClient, user_id: int, db_sessionmaker: sessionmaker
):
    """越权防护：只能看到自己的记录（方案 §12.3）。"""
    _seed_rounds(record_client, user_id, count=2)

    from app.db.orm_models import User

    with db_sessionmaker() as session:
        other = User(openid="openid-other")
        session.add(other)
        session.commit()
        other_id = other.id

    resp = record_client.get(
        "/api/v1/quiz/records", headers=auth_header(other_id)
    )
    assert resp.json()["data"] == {"total": 0, "records": []}


# ---------- 基础统计（方案 §8.2） ----------


def test_stats_requires_login(record_client: TestClient):
    resp = record_client.get("/api/v1/user/stats")
    assert resp.json()["code"] == 4010


def test_stats_empty_user(record_client: TestClient, user_id: int):
    resp = record_client.get("/api/v1/user/stats", headers=auth_header(user_id))
    assert resp.json()["data"] == {
        "total_count": 0,
        "avg_accuracy": 0,
        "total_xp": 0,
    }


def test_stats_values(record_client: TestClient, user_id: int):
    # 第1局 4 对（80%，+40），第2局 2 对（40%，+20）
    q1 = make_questions(5)
    submit(
        record_client, user_id, q1, make_answers(q1, {"q2"}),
        client_record_id="s1",
    )
    q2 = make_questions(5)
    submit(
        record_client, user_id, q2, make_answers(q2, {"q2", "q3", "q4"}),
        client_record_id="s2",
    )

    resp = record_client.get("/api/v1/user/stats", headers=auth_header(user_id))
    assert resp.json()["data"] == {
        "total_count": 2,
        "avg_accuracy": 60,  # round((80 + 40) / 2)
        "total_xp": 60,
    }


# ---------- 题目明细与报告落库 ----------


def test_submit_persists_question_items_with_recomputed_correctness(
    record_client: TestClient, user_id: int, db_sessionmaker: sessionmaker
):
    questions = make_questions(5)
    # q2 实际选错，但 is_correct 伪造为 True
    answers = make_answers(questions, {"q2"})
    body = submit(record_client, user_id, questions, answers, client_record_id="items-1")
    assert body["code"] == 0

    from app.db.orm_models import QuizQuestionRecord

    with db_sessionmaker() as session:
        items = (
            session.query(QuizQuestionRecord)
            .order_by(QuizQuestionRecord.question_index)
            .all()
        )
        assert len(items) == 5
        first = items[0]
        assert first.question_id == "q1"
        assert first.question_index == 0
        assert first.qtype == "single"
        assert first.stem == "第1题：哪个说法正确？"
        assert first.options == [
            {"key": "A", "text": "正确项"},
            {"key": "B", "text": "干扰项"},
        ]
        assert first.answer == ["A"]
        assert first.explanation == "A 是正确项。"
        assert first.knowledge_point == "知识点1"
        assert first.selected_answers == ["A"]
        assert first.is_correct is True
        assert first.duration_ms == 1200
        # q2 实际选 B：库内必须是服务端复算的 False，忽略伪造值
        assert items[1].question_id == "q2"
        assert items[1].selected_answers == ["B"]
        assert items[1].is_correct is False


def test_submit_with_report_persists_and_overrides_accuracy(
    record_client: TestClient, user_id: int, db_sessionmaker: sessionmaker
):
    questions = make_questions(5)
    answers = make_answers(questions, {"q2"})  # 复算 accuracy=80
    body = submit(
        record_client, user_id, questions, answers,
        client_record_id="rep-1", report=make_report_payload(accuracy=99),
    )
    assert body["code"] == 0

    from app.db.orm_models import QuizReport

    with db_sessionmaker() as session:
        report = session.query(QuizReport).one()
        assert report.accuracy == 80  # 服务端复算覆盖伪造的 99
        assert report.mastered_points == ["知识点1"]
        assert report.weak_points == ["知识点2"]
        assert report.three_line_summary == ["第一句", "第二句", "第三句"]
        assert report.advice == ["多复习"]
        assert report.share_quote == "温故而知新"
        assert report.user_id == user_id


def test_submit_without_report_writes_no_report_row(
    record_client: TestClient, user_id: int, db_sessionmaker: sessionmaker
):
    """兼容旧客户端：不带 report 字段时不写报告行。"""
    questions = make_questions(5)
    submit(
        record_client, user_id, questions, make_answers(questions, set()),
        client_record_id="no-rep",
    )

    from app.db.orm_models import QuizReport

    with db_sessionmaker() as session:
        assert session.query(QuizReport).count() == 0


def test_idempotent_replay_does_not_duplicate_items_and_report(
    record_client: TestClient, user_id: int, db_sessionmaker: sessionmaker
):
    questions = make_questions(5)
    answers = make_answers(questions, {"q2"})
    submit(
        record_client, user_id, questions, answers,
        client_record_id="dup-full", report=make_report_payload(80),
    )
    replay = submit(
        record_client, user_id, questions, make_answers(questions, set()),
        client_record_id="dup-full", report=make_report_payload(100),
    )
    assert replay["data"]["duplicated"] is True

    from app.db.orm_models import QuizQuestionRecord, QuizReport

    with db_sessionmaker() as session:
        assert session.query(QuizQuestionRecord).count() == 5
        assert session.query(QuizReport).count() == 1


# ---------- 记录详情（逐题明细 + 报告） ----------


def _seed_detail(client: TestClient, uid: int) -> int:
    questions = make_questions(5)
    answers = make_answers(questions, {"q2"})
    body = submit(
        client, uid, questions, answers,
        client_record_id="detail-1", report=make_report_payload(),
    )
    return body["data"]["record_id"]


def test_record_detail_requires_login(record_client: TestClient):
    resp = record_client.get("/api/v1/quiz/records/1")
    assert resp.json()["code"] == 4010


def test_record_detail_returns_items_in_order_and_report(
    record_client: TestClient, user_id: int
):
    record_id = _seed_detail(record_client, user_id)
    resp = record_client.get(
        f"/api/v1/quiz/records/{record_id}", headers=auth_header(user_id)
    )
    data = resp.json()["data"]
    assert data["record"]["record_id"] == record_id
    assert data["record"]["accuracy"] == 80

    qs = data["questions"]
    assert [q["question_index"] for q in qs] == [0, 1, 2, 3, 4]
    assert qs[0]["question_id"] == "q1"
    assert qs[0]["type"] == "single"
    assert qs[0]["is_correct"] is True
    assert qs[1]["question_id"] == "q2"
    assert qs[1]["is_correct"] is False
    assert qs[1]["selected_answers"] == ["B"]
    assert qs[1]["options"][0]["key"] == "A"

    report = data["report"]
    assert report["accuracy"] == 80
    assert report["share_quote"] == "温故而知新"


def test_record_detail_without_report_returns_null(
    record_client: TestClient, user_id: int
):
    questions = make_questions(2)
    body = submit(
        record_client, user_id, questions, make_answers(questions, set()),
        client_record_id="detail-norep",
    )
    record_id = body["data"]["record_id"]
    resp = record_client.get(
        f"/api/v1/quiz/records/{record_id}", headers=auth_header(user_id)
    )
    data = resp.json()["data"]
    assert data["report"] is None
    assert len(data["questions"]) == 2


def test_record_detail_not_found_returns_4001(
    record_client: TestClient, user_id: int
):
    resp = record_client.get(
        "/api/v1/quiz/records/99999", headers=auth_header(user_id)
    )
    assert resp.json()["code"] == 4001


def test_record_detail_other_users_record_returns_4001(
    record_client: TestClient, user_id: int, db_sessionmaker: sessionmaker
):
    """越权防护：他人记录与不存在统一 4001，不暴露记录存在性（§12.3）。"""
    record_id = _seed_detail(record_client, user_id)

    from app.db.orm_models import User

    with db_sessionmaker() as session:
        other = User(openid="openid-detail-other")
        session.add(other)
        session.commit()
        other_id = other.id

    resp = record_client.get(
        f"/api/v1/quiz/records/{record_id}", headers=auth_header(other_id)
    )
    assert resp.json()["code"] == 4001
