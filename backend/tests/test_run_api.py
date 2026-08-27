"""API tests for the workflow execution endpoints (RDA-033)."""

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints.run import _nodes_factory, _orchestrator
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.orchestration.nodes import ResearchNodes
from app.services.orchestration.orchestrator import ResearchOrchestrator

BASE = f"{settings.API_V1_PREFIX}/researches"


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    # In-memory SQLite so the run/status endpoints do not depend on a real
    # database (the run endpoint queries the researches table).
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

    orchestrator = ResearchOrchestrator()
    app.dependency_overrides[_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_run_and_status(client: TestClient) -> None:
    # A run requires a persisted research (RDA-056); a non-existent id must
    # not fabricate a COMPLETED state.
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

    def fake_nodes_factory():
        def build(session, rid):
            return ResearchNodes()

        return build

    app.dependency_overrides[_nodes_factory] = fake_nodes_factory

    run_resp = client.post(f"{BASE}/{research_id}/run")

    assert run_resp.status_code == 200, run_resp.text
    body = run_resp.json()
    assert body["current_stage"] == "COMPLETED"
    assert body["research_id"] == str(research_id)

    status_resp = client.get(f"{BASE}/{research_id}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["execution_id"] == body["execution_id"]


def test_run_unknown_returns_404(client: TestClient) -> None:
    resp = client.post(f"{BASE}/{uuid.uuid4()}/run")
    assert resp.status_code == 404


def test_status_unknown_returns_404(client: TestClient) -> None:
    resp = client.get(f"{BASE}/{uuid.uuid4()}/status")
    assert resp.status_code == 404
