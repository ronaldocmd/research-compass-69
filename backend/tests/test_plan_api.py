"""API tests for the research plan endpoints (RDA-031)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints.plan import _planner
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.llm.provider import LLMProvider
from app.services.planning.planner import ResearchPlanner
from app.services.planning.schemas import PlanTaskDraft

BASE = f"{settings.API_V1_PREFIX}/researches"


class _FakeLLMProvider(LLMProvider):
    name = "fake"

    def __init__(self, tasks) -> None:
        self.model = "fake-model"
        self._tasks = tasks

    def complete(self, prompt, response_model):
        return response_model(tasks=self._tasks)


def _draft(title: str, priority: int = 1) -> PlanTaskDraft:
    return PlanTaskDraft(
        title=title, description=f"{title} desc", priority=priority, task_type="SEARCH"
    )


@pytest.fixture
def client():
    # StaticPool + check_same_thread=False lets a single in-memory SQLite DB
    # be shared across the TestClient worker threads (needed because FastAPI
    # runs sync endpoints in a threadpool).
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_planner():
        return ResearchPlanner(
            llm=_FakeLLMProvider(
                tasks=[_draft("high", 1), _draft("mid", 2), _draft("low", 3)]
            )
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_planner] = override_planner
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def _create_research(client: TestClient) -> str:
    resp = client.post(BASE, json={"title": "T", "objective": "O", "question": "Q"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_create_plan_endpoint(client: TestClient) -> None:
    research_id = _create_research(client)

    resp = client.post(f"{BASE}/{research_id}/plan", json={"depth": "standard"})

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "CREATED"
    assert len(body["tasks"]) == 3


def test_get_plan_returns_tasks_ordered_by_priority(client: TestClient) -> None:
    research_id = _create_research(client)
    client.post(f"{BASE}/{research_id}/plan", json={})

    resp = client.get(f"{BASE}/{research_id}/plan")

    assert resp.status_code == 200
    assert [t["title"] for t in resp.json()["tasks"]] == ["high", "mid", "low"]


def test_list_tasks_endpoint(client: TestClient) -> None:
    research_id = _create_research(client)
    client.post(f"{BASE}/{research_id}/plan", json={})

    resp = client.get(f"{BASE}/{research_id}/plan/tasks")

    assert resp.status_code == 200
    assert [t["title"] for t in resp.json()] == ["high", "mid", "low"]


def test_get_plan_missing_returns_404(client: TestClient) -> None:
    research_id = _create_research(client)

    assert client.get(f"{BASE}/{research_id}/plan").status_code == 404
