"""API tests for human evaluation (RDA-049).

Uses an in-memory SQLite database with the ``human_evaluations`` table so the
full API -> Repository -> DB path is exercised without PostgreSQL.
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

BASE = "/api/v1/evaluations"


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    # StaticPool + check_same_thread=False share one in-memory DB across the
    # TestClient thread and the request threads.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables["human_evaluations"]]
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


def _payload(
    claim_id: uuid.UUID | None = None,
    research_id: uuid.UUID | None = None,
    rating: str = "correct",
    evaluator_id: str = "evaluator@example.com",
    comment: str | None = None,
) -> dict:
    return {
        "claim_id": str(claim_id or uuid.uuid4()),
        "research_id": str(research_id or uuid.uuid4()),
        "evaluator_id": evaluator_id,
        "rating": rating,
        "comment": comment,
    }


def test_create_evaluation_returns_201(client: TestClient) -> None:
    payload = _payload(comment="Evidência sólida")

    response = client.post(BASE, json=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    uuid.UUID(body["id"])
    assert body["claim_id"] == payload["claim_id"]
    assert body["research_id"] == payload["research_id"]
    assert body["evaluator_id"] == payload["evaluator_id"]
    assert body["rating"] == "correct"
    assert body["comment"] == "Evidência sólida"
    assert body["evaluated_at"]


def test_create_evaluation_rejects_invalid_rating(client: TestClient) -> None:
    response = client.post(BASE, json=_payload(rating="maybe"))

    assert response.status_code == 422


def test_create_evaluation_rejects_missing_fields(client: TestClient) -> None:
    response = client.post(BASE, json={"rating": "correct"})

    assert response.status_code == 422


def test_list_evaluations_by_claim(client: TestClient) -> None:
    claim_id = uuid.uuid4()
    client.post(BASE, json=_payload(claim_id=claim_id))
    client.post(BASE, json=_payload(claim_id=claim_id, rating="incorrect"))
    client.post(BASE, json=_payload())

    response = client.get(BASE, params={"claim_id": str(claim_id)})

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert all(item["claim_id"] == str(claim_id) for item in items)


def test_list_evaluations_by_research(client: TestClient) -> None:
    research_id = uuid.uuid4()
    client.post(BASE, json=_payload(research_id=research_id))
    client.post(BASE, json=_payload(research_id=research_id, rating="inconclusive"))
    client.post(BASE, json=_payload())

    response = client.get(f"/api/v1/researches/{research_id}/evaluations")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert all(item["research_id"] == str(research_id) for item in items)


def test_evaluation_stats(client: TestClient) -> None:
    research_id = uuid.uuid4()
    client.post(BASE, json=_payload(research_id=research_id, rating="correct"))
    client.post(BASE, json=_payload(research_id=research_id, rating="correct"))
    client.post(BASE, json=_payload(research_id=research_id, rating="incorrect"))
    client.post(BASE, json=_payload(research_id=research_id, rating="inconclusive"))

    response = client.get(f"/api/v1/researches/{research_id}/evaluation-stats")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    assert body["correct"] == 0.5
    assert body["incorrect"] == 0.25
    assert body["inconclusive"] == 0.25


def test_evaluation_stats_empty(client: TestClient) -> None:
    response = client.get(f"/api/v1/researches/{uuid.uuid4()}/evaluation-stats")

    assert response.status_code == 200
    assert response.json() == {
        "total": 0,
        "correct": 0.0,
        "incorrect": 0.0,
        "inconclusive": 0.0,
    }


def test_multiple_evaluations_per_claim_are_kept(client: TestClient) -> None:
    claim_id = uuid.uuid4()
    research_id = uuid.uuid4()
    first = client.post(
        BASE, json=_payload(claim_id=claim_id, research_id=research_id, rating="correct")
    ).json()
    second = client.post(
        BASE,
        json=_payload(
            claim_id=claim_id,
            research_id=research_id,
            rating="incorrect",
            evaluator_id="second@example.com",
        ),
    ).json()

    items = client.get(BASE, params={"claim_id": str(claim_id)}).json()

    assert len(items) == 2
    assert {item["id"] for item in items} == {first["id"], second["id"]}
