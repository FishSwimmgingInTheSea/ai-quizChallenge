"""接口契约测试：health / quiz(sync + async 轮询) / report。

通过 dependency_overrides 注入 mock 生成器与隔离的任务存储，不触碰真实模型。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_quiz_service, get_report_service, get_store
from app.main import create_app
from app.services.quiz_service import QuizService
from app.services.report_service import ReportService
from app.services.task_store import TaskStore
from tests.conftest import (
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
