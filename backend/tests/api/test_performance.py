"""API tests for the research performance endpoint (RDA-051).

Uses an in-memory SQLite database with the ``researches`` and
``performance_metrics`` tables so the full API -> Tracker -> DB path is
exercised.
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
from app.services.performance.tracker import PerformanceTracker

BASE = "/api/v1/researches"


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Base.metadata.tables["researches"],
            Base.metadata.tables["performance_metrics"],
        ],
    )
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


def test_performance_returns_empty_report(client: TestClient) -> None:
    research_id = _create_research(client)

    response = client.get(f"{BASE}/{research_id}/performance")

    assert response.status_code == 200
    body = response.json()
    assert body["research_id"] == str(research_id)
    assert body["time_to_first_result"] is None
    assert body["time_to_completion"] == 0.0
    assert body["documents_found"] == 0
    assert body["documents_processed"] == 0
    assert body["throughput_docs_per_minute"] == 0.0
    assert body["error_rate"] == 0.0
    assert body["stages"] == []


def test_performance_returns_tracked_stages(client: TestClient) -> None:
    research_id = _create_research(client)
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        tracker = PerformanceTracker(db)
        tracker.start_stage(research_id, "planning")
        tracker.end_stage(research_id, "planning")
        tracker.start_stage(research_id, "search")
        tracker.end_stage(research_id, "search")
    finally:
        gen.close()

    response = client.get(f"{BASE}/{research_id}/performance")

    assert response.status_code == 200
    body = response.json()
    assert body["time_to_first_result"] is not None
    assert body["time_to_completion"] >= 0
    assert len(body["stages"]) == 2
    assert {s["stage"] for s in body["stages"]} == {"planning", "search"}
    assert all(s["status"] == "success" for s in body["stages"])


def test_performance_404_for_unknown_research(client: TestClient) -> None:
    response = client.get(f"{BASE}/{uuid.uuid4()}/performance")

    assert response.status_code == 404
