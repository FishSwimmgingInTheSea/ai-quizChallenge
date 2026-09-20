"""接口契约测试：health / quiz(sync + async 轮询) / report / 知识库出题。

通过 dependency_overrides 注入 mock 生成器与隔离的任务存储，不触碰真实模型。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.deps import (
    get_kb_service,
    get_quiz_service,
    get_report_service,
    get_store,
)
from app.core.security import create_token
from app.main import create_app
from app.services.kb_service import KbService
from app.services.quiz_service import QuizService
from app.services.report_service import ReportService
from app.services.task_store import TaskStore
from tests.conftest import (
    FakeKbStore,
    FakeQuizGenerator,
    FakeReportGenerator,
    FakeResearchService,
)


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    store = TaskStore(ttl_seconds=300)
    app.dependency_overrides[get_quiz_service] = lambda: QuizService(
        generator=FakeQuizGenerator(),
        # 注入受控研究 mock：不依赖环境 .env 是否配置 TAVILY_API_KEY
        research=FakeResearchService(),
    )
    app.dependency_overrides[get_report_service] = lambda: ReportService(
        generator=FakeReportGenerator()
    )
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)


def test_health(client: TestClient):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "up"


def test_generate_sync_returns_full_quiz(client: TestClient):
    resp = client.post(
        "/api/v1/quiz/generate/sync",
        json={"user_input": "什么是 RAG", "question_count": 5},
    )
    body = resp.json()
    assert body["code"] == 0
    assert len(body["data"]["questions"]) == 5
    assert body["data"]["quiz_id"].startswith("quiz_")


def test_generate_sync_rejects_short_input(client: TestClient):
    resp = client.post(
        "/api/v1/quiz/generate/sync",
        json={"user_input": "x"},
    )
    body = resp.json()
    assert body["code"] == 4001


def test_generate_sync_rejects_sensitive_input(client: TestClient):
    resp = client.post(
        "/api/v1/quiz/generate/sync",
        json={"user_input": "如何进行赌博活动"},
    )
    body = resp.json()
    assert body["code"] == 4002


def test_async_generate_then_poll(client: TestClient):
    submit = client.post(
        "/api/v1/quiz/generate",
        json={"user_input": "什么是 RAG", "question_count": 5},
    )
    sbody = submit.json()
    assert sbody["code"] == 0
    task_id = sbody["data"]["task_id"]
    assert sbody["data"]["status"] == "pending"

    # 后台任务在 TestClient 返回前已完成
    poll = client.get(f"/api/v1/quiz/task/{task_id}")
    pbody = poll.json()
    assert pbody["code"] == 0
    assert pbody["data"]["status"] == "done"
    assert pbody["data"]["generated_count"] == 5
    assert pbody["data"]["total"] == 5
    # 新增阶段字段（quiz-web-search-grounding D7）：任务完成后 phase 回到 generating，
    # research_used 反映 mock 研究降级；旧前端忽略新字段不受影响
    assert pbody["data"]["phase"] == "generating"
    assert pbody["data"]["research_used"] is False


def test_poll_unknown_task_returns_4004(client: TestClient):
    resp = client.get("/api/v1/quiz/task/task_not_exist")
    body = resp.json()
    assert body["code"] == 4004


def test_report_generate(client: TestClient):
    questions = [
        {
            "id": "q1",
            "type": "single",
            "stem": "题",
            "options": [{"key": "A", "text": "a"}, {"key": "B", "text": "b"}],
            "answer": ["A"],
            "explanation": "讲解",
            "knowledge_point": "概念",
            "difficulty": "easy",
        }
    ]
    resp = client.post(
        "/api/v1/report/generate",
        json={
            "quiz_id": "quiz_1",
            "topic": "RAG 入门",
            "questions": questions,
            "answer_records": [
                {
                    "question_id": "q1",
                    "selected_answers": ["A"],
                    "is_correct": True,
                    "duration_ms": 3200,
                }
            ],
        },
    )
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["accuracy"] == 100
    assert len(body["data"]["three_line_summary"]) == 3


# ---------- 知识库出题链路（kb-rag：可选登录 + 文档校验 + 传参） ----------


def auth_header(uid: int) -> dict:
    return {"Authorization": f"Bearer {create_token(uid)}"}


def make_user(db: sessionmaker) -> int:
    from uuid import uuid4

    from app.db.orm_models import User

    with db() as session:
        user = User(openid=f"openid-kb-quiz-{uuid4().hex[:8]}")
        session.add(user)
        session.commit()
        return user.id


def make_kb_doc(db: sessionmaker, user_id: int, status: str = "ready") -> int:
    from app.db.orm_models import KbDocument

    with db() as session:
        doc = KbDocument(
            user_id=user_id,
            filename="handbook.txt",
            doc_type="txt",
            file_size=32,
            status=status,
        )
        session.add(doc)
        session.commit()
        return doc.id


@pytest.fixture
def kb_env(db_sessionmaker: sessionmaker) -> SimpleNamespace:
    """可选登录出题环境：TestClient + 受控研究 mock + 内存库知识库服务。"""
    from app.api.deps import get_db

    app = create_app()
    store = TaskStore(ttl_seconds=300)
    research = FakeResearchService()
    app.dependency_overrides[get_quiz_service] = lambda: QuizService(
        generator=FakeQuizGenerator(), research=research
    )
    app.dependency_overrides[get_store] = lambda: store

    def override_db():
        session = db_sessionmaker()
        try:
            yield session
        finally:
            session.close()

    def override_kb_service():
        return KbService(db_sessionmaker(), FakeKbStore())

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_kb_service] = override_kb_service
    return SimpleNamespace(
        client=TestClient(app), research=research, db=db_sessionmaker
    )


def test_generate_with_kb_doc_ids_requires_login(kb_env):
    resp = kb_env.client.post(
        "/api/v1/quiz/generate",
        json={"user_input": "员工手册考核", "kb_doc_ids": [1]},
    )
    assert resp.json()["code"] == 4010


def test_generate_with_kb_doc_ids_passes_to_research(kb_env):
    uid = make_user(kb_env.db)
    doc_id = make_kb_doc(kb_env.db, uid)
    resp = kb_env.client.post(
        "/api/v1/quiz/generate",
        json={"user_input": "员工手册考核", "kb_doc_ids": [doc_id]},
        headers=auth_header(uid),
    )
    sbody = resp.json()
    assert sbody["code"] == 0
    task_id = sbody["data"]["task_id"]

    poll = kb_env.client.get(f"/api/v1/quiz/task/{task_id}")
    pbody = poll.json()
    assert pbody["code"] == 0
    assert pbody["data"]["status"] == "done"
    # 研究服务收到用户身份与选中的文档集合（Agentic RAG 传参链路）
    assert kb_env.research.call_kwargs == [
        {"user_id": uid, "kb_doc_ids": [doc_id]}
    ]


def test_generate_without_kb_sends_none_to_research(kb_env):
    resp = kb_env.client.post(
        "/api/v1/quiz/generate",
        json={"user_input": "什么是 RAG"},
    )
    assert resp.json()["code"] == 0
    # 匿名普通出题：传参链路与原有行为完全一致（回归保护）
    assert kb_env.research.call_kwargs == [{"user_id": None, "kb_doc_ids": None}]


def test_generate_with_not_ready_doc_rejected(kb_env):
    uid = make_user(kb_env.db)
    doc_id = make_kb_doc(kb_env.db, uid, status="processing")
    resp = kb_env.client.post(
        "/api/v1/quiz/generate",
        json={"user_input": "员工手册考核", "kb_doc_ids": [doc_id]},
        headers=auth_header(uid),
    )
    # 文档未处理完成：同步快失败 4001，不进入后台任务
    assert resp.json()["code"] == 4001
    assert kb_env.research.calls == 0


def test_generate_with_foreign_doc_rejected(kb_env):
    uid = make_user(kb_env.db)
    other_id = make_user(kb_env.db)
    doc_id = make_kb_doc(kb_env.db, other_id)  # 他人文档
    resp = kb_env.client.post(
        "/api/v1/quiz/generate",
        json={"user_input": "员工手册考核", "kb_doc_ids": [doc_id]},
        headers=auth_header(uid),
    )
    # 越权选择他人文档：4001
    assert resp.json()["code"] == 4001
    assert kb_env.research.calls == 0


def test_generate_kb_doc_ids_over_limit(kb_env):
    uid = make_user(kb_env.db)
    resp = kb_env.client.post(
        "/api/v1/quiz/generate",
        json={"user_input": "员工手册考核", "kb_doc_ids": list(range(1, 12))},
        headers=auth_header(uid),
    )
    # 最多选 10 个文档：超限请求参数不合法
    assert resp.json()["code"] == 4001


def test_generate_sync_with_kb_doc_ids_passes_to_research(kb_env):
    uid = make_user(kb_env.db)
    doc_id = make_kb_doc(kb_env.db, uid)
    resp = kb_env.client.post(
        "/api/v1/quiz/generate/sync",
        json={"user_input": "员工手册考核", "kb_doc_ids": [doc_id]},
        headers=auth_header(uid),
    )
    body = resp.json()
    assert body["code"] == 0
    assert len(body["data"]["questions"]) == 5
    assert kb_env.research.call_kwargs == [
        {"user_id": uid, "kb_doc_ids": [doc_id]}
    ]


# ---------- 知识库自动出题（空输入 + 选中文档） ----------


def test_generate_empty_input_without_kb_rejected(kb_env):
    resp = kb_env.client.post("/api/v1/quiz/generate", json={"user_input": ""})
    # 空输入又未选知识库：无从出题，参数不合法
    assert resp.json()["code"] == 4001
    assert kb_env.research.calls == 0


def test_generate_empty_input_with_kb_accepted(kb_env):
    uid = make_user(kb_env.db)
    doc_id = make_kb_doc(kb_env.db, uid)
    resp = kb_env.client.post(
        "/api/v1/quiz/generate",
        json={"user_input": "", "kb_doc_ids": [doc_id]},
        headers=auth_header(uid),
    )
    sbody = resp.json()
    assert sbody["code"] == 0
    poll = kb_env.client.get(f"/api/v1/quiz/task/{sbody['data']['task_id']}")
    assert poll.json()["data"]["status"] == "done"
    # 空输入原样传给研究服务（自动推断主题发生在真实 ResearchService 内部）
    assert kb_env.research.inputs == [""]
    assert kb_env.research.call_kwargs == [
        {"user_id": uid, "kb_doc_ids": [doc_id]}
    ]


def test_generate_sync_empty_input_with_kb_accepted(kb_env):
    uid = make_user(kb_env.db)
    doc_id = make_kb_doc(kb_env.db, uid)
    resp = kb_env.client.post(
        "/api/v1/quiz/generate/sync",
        json={"user_input": "", "kb_doc_ids": [doc_id]},
        headers=auth_header(uid),
    )
    body = resp.json()
    assert body["code"] == 0
    assert len(body["data"]["questions"]) == 5
