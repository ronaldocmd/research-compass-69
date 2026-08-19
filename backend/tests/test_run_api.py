"""API tests for the workflow execution endpoints (RDA-033)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.run import _orchestrator
from app.core.config import settings
from app.main import app
from app.services.orchestration.orchestrator import ResearchOrchestrator

BASE = f"{settings.API_V1_PREFIX}/researches"


@pytest.fixture
def client():
    orchestrator = ResearchOrchestrator()
    app.dependency_overrides[_orchestrator] = lambda: orchestrator
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_run_and_status(client: TestClient) -> None:
    research_id = uuid.uuid4()

    run_resp = client.post(f"{BASE}/{research_id}/run")

    assert run_resp.status_code == 200, run_resp.text
    body = run_resp.json()
    assert body["current_stage"] == "COMPLETED"
    assert body["research_id"] == str(research_id)

    status_resp = client.get(f"{BASE}/{research_id}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["execution_id"] == body["execution_id"]


def test_status_unknown_returns_404(client: TestClient) -> None:
    resp = client.get(f"{BASE}/{uuid.uuid4()}/status")
    assert resp.status_code == 404
