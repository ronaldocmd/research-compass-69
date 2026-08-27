"""API tests for the evidence chain endpoint (RDA-061)."""

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

BASE = f"{settings.API_V1_PREFIX}/researches"


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
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


def test_evidence_chain_empty_for_research_without_chain(client: TestClient) -> None:
    created = client.post(
        BASE,
        json={
            "title": "Impacto de LLMs",
            "objective": "Mapear literatura",
            "question": "Qual o estado da arte?",
        },
    )
    assert created.status_code == 201, created.text
    research_id = created.json()["id"]

    resp = client.get(f"{BASE}/{research_id}/evidence")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["research_id"] == str(research_id)
    assert body["claims"] == []
    assert body["evidence"] == []
    assert body["validations"] == []
    assert body["provenance"] == []
    assert body["confidence"] == []


def test_evidence_chain_unknown_research_returns_404(client: TestClient) -> None:
    resp = client.get(f"{BASE}/{uuid.uuid4()}/evidence")
    assert resp.status_code == 404
