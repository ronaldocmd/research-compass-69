"""API tests for the research cost endpoint (RDA-050).

Uses an in-memory SQLite database with the ``researches`` and ``usage_events``
tables so the full API -> Service -> Tracker -> DB path is exercised.
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
from app.services.usage.tracker import UsageTracker

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
            Base.metadata.tables["usage_events"],
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
            "title": "Custo de LLMs",
            "objective": "Medir custo",
            "question": "Quanto custa?",
        },
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def test_cost_endpoint_returns_empty_report(client: TestClient) -> None:
    research_id = _create_research(client)

    response = client.get(f"{BASE}/{research_id}/cost")

    assert response.status_code == 200
    body = response.json()
    assert body["research_id"] == str(research_id)
    assert body["llm_calls"] == 0
    assert body["total_tokens"] == 0
    assert body["search_calls"] == 0
    assert body["processing_operations"] == 0
    assert body["estimated_cost_usd"] == 0.0


def test_cost_endpoint_returns_aggregated_report(client: TestClient) -> None:
    research_id = _create_research(client)
    # Seed usage events directly through the tracker (same DB via override).
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        tracker = UsageTracker(db)
        tracker.record_llm_call(research_id, "gpt-4", 1000, 1000)  # 0.09
        tracker.record_llm_call(research_id, "gpt-3.5-turbo", 1000, 1000)  # 0.0035
        tracker.record_search_call(research_id, "openalex")
        tracker.record_processing(research_id, documents=1, chunks=4, embeddings=4)
    finally:
        gen.close()

    response = client.get(f"{BASE}/{research_id}/cost")

    assert response.status_code == 200
    body = response.json()
    assert body["llm_calls"] == 2
    assert body["total_tokens"] == 4000
    assert body["search_calls"] == 1
    assert body["processing_operations"] == 1
    assert body["estimated_cost_usd"] == pytest.approx(0.0935)


def test_cost_endpoint_404_for_unknown_research(client: TestClient) -> None:
    response = client.get(f"{BASE}/{uuid.uuid4()}/cost")

    assert response.status_code == 404
