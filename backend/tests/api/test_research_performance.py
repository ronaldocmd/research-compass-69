"""API tests for research performance/timing (RDA-051).

Uses an in-memory SQLite database with the ``researches`` table.
"""

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.orchestration.orchestrator import ResearchOrchestrator
from app.api.v1.endpoints.run import _orchestrator

BASE = "/api/v1/researches"


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine, tables=[Base.metadata.tables["researches"]])
    factory: sessionmaker[Session] = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    def override_get_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_orchestrator] = lambda: ResearchOrchestrator()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def _create_research(client: TestClient) -> uuid.UUID:
    response = client.post(
        BASE,
        json={
            "title": "Performance",
            "objective": "Medir tempo",
            "question": "Quanto tempo?",
        },
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def test_performance_returns_null_before_run(client: TestClient) -> None:
    research_id = _create_research(client)

    response = client.get(f"{BASE}/{research_id}/performance")

    assert response.status_code == 200
    body = response.json()
    assert body["research_id"] == str(research_id)
    assert body["started_at"] is None
    assert body["completed_at"] is None
    assert body["duration_seconds"] is None


def test_run_persists_timing_and_performance_returns_duration(
    client: TestClient,
) -> None:
    research_id = _create_research(client)

    run_resp = client.post(f"{BASE}/{research_id}/run")
    assert run_resp.status_code == 200, run_resp.text

    response = client.get(f"{BASE}/{research_id}/performance")

    assert response.status_code == 200
    body = response.json()
    assert body["started_at"] is not None
    assert body["completed_at"] is not None
    assert body["duration_seconds"] is not None
    assert body["duration_seconds"] >= 0


def test_performance_404_for_unknown_research(client: TestClient) -> None:
    response = client.get(f"{BASE}/{uuid.uuid4()}/performance")

    assert response.status_code == 404
