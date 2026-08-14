"""Unit + integration tests for the Research API (RDA-006).

Integration tests run against a real PostgreSQL when RDA_TEST_DATABASE_URL is
set (see conftest.pg_client); otherwise they are skipped.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.research import ResearchCreate, ResearchUpdate

BASE = f"{settings.API_V1_PREFIX}/researches"

PAYLOAD = {
    "title": "Impacto de LLMs na revisão sistemática",
    "objective": "Mapear evidências recentes",
    "question": "Como LLMs afetam a triagem de artigos?",
}


# --- unit tests (schemas / business rules, no database) -------------------


def test_create_schema_defaults_to_draft() -> None:
    assert ResearchCreate(**PAYLOAD).status.value == "DRAFT"


def test_create_schema_rejects_title_over_200() -> None:
    with pytest.raises(ValidationError):
        ResearchCreate(**{**PAYLOAD, "title": "x" * 201})


def test_create_schema_requires_fields() -> None:
    with pytest.raises(ValidationError):
        ResearchCreate(title="only title")  # type: ignore[call-arg]


def test_create_schema_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        ResearchCreate(**{**PAYLOAD, "status": "ARCHIVED"})


def test_update_schema_is_partial() -> None:
    assert ResearchUpdate(status="READY").model_dump(exclude_unset=True) == {"status": "READY"}


# --- integration tests (real PostgreSQL) ---------------------------------


def test_full_crud_round_trip(pg_client: TestClient) -> None:
    created = pg_client.post(BASE, json=PAYLOAD)
    assert created.status_code == 201, created.text
    body = created.json()
    research_id = body["id"]
    uuid.UUID(research_id)
    assert body["status"] == "DRAFT"
    assert body["created_at"] and body["updated_at"]

    listed = pg_client.get(BASE)
    assert listed.status_code == 200
    assert research_id in [item["id"] for item in listed.json()]

    fetched = pg_client.get(f"{BASE}/{research_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == PAYLOAD["title"]

    patched = pg_client.patch(f"{BASE}/{research_id}", json={"status": "READY", "title": "Novo título"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "READY"
    assert patched.json()["title"] == "Novo título"

    deleted = pg_client.delete(f"{BASE}/{research_id}")
    assert deleted.status_code == 204
    assert pg_client.get(f"{BASE}/{research_id}").status_code == 404


def test_get_unknown_id_returns_404(pg_client: TestClient) -> None:
    assert pg_client.get(f"{BASE}/{uuid.uuid4()}").status_code == 404


def test_patch_unknown_id_returns_404(pg_client: TestClient) -> None:
    assert pg_client.patch(f"{BASE}/{uuid.uuid4()}", json={"status": "READY"}).status_code == 404


def test_delete_unknown_id_returns_404(pg_client: TestClient) -> None:
    assert pg_client.delete(f"{BASE}/{uuid.uuid4()}").status_code == 404


def test_invalid_uuid_returns_422(pg_client: TestClient) -> None:
    assert pg_client.get(f"{BASE}/not-a-uuid").status_code == 422


def test_create_validation_errors(pg_client: TestClient) -> None:
    assert pg_client.post(BASE, json={"title": "no objective"}).status_code == 422
    assert pg_client.post(BASE, json={**PAYLOAD, "title": "x" * 201}).status_code == 422
    assert pg_client.post(BASE, json={**PAYLOAD, "status": "ARCHIVED"}).status_code == 422


def test_patch_invalid_status_returns_422(pg_client: TestClient) -> None:
    created = pg_client.post(BASE, json=PAYLOAD).json()
    assert pg_client.patch(f"{BASE}/{created['id']}", json={"status": "DONE"}).status_code == 422
    pg_client.delete(f"{BASE}/{created['id']}")


def test_pagination_and_health_still_work(pg_client: TestClient) -> None:
    ids = [pg_client.post(BASE, json={**PAYLOAD, "title": f"R{i}"}).json()["id"] for i in range(3)]
    page = pg_client.get(BASE, params={"limit": 2, "offset": 0})
    assert page.status_code == 200
    assert len(page.json()) == 2
    assert pg_client.get("/health").status_code == 200
    assert pg_client.get(f"{settings.API_V1_PREFIX}/health").json()["database"] == "up"
    for research_id in ids:
        pg_client.delete(f"{BASE}/{research_id}")
