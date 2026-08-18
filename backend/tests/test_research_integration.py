"""Integration tests for the Research API flow (RDA-006).

Uses an in-memory SQLite database via dependency override to exercise the
full path: API -> Service -> Repository -> Database.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Research
from app.models.research import ResearchStatus
from app.schemas.research import ResearchCreate, ResearchUpdate
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Research.__table__.create(engine, checkfirst=True)
    
    with engine.connect() as conn:
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='researches'"))
        tables = result.fetchall()
        print(f"TABLES AFTER CREATE_ALL: {tables}")
    
    factory: sessionmaker[Session] = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_get_db() -> Session:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_health_check_with_sqlite(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"


def test_create_and_list_research(client: TestClient) -> None:
    payload = {
        "title": "Impacto de LLMs",
        "objective": "Mapear evidências",
        "question": "Como LLMs afetam a revisão?",
        "status": "DRAFT",
    }

    created = client.post("/api/v1/researches", json=payload)
    assert created.status_code == 201
    body = created.json()
    research_id = body["id"]
    uuid.UUID(research_id)
    assert body["title"] == payload["title"]
    assert body["status"] == "DRAFT"
    assert body["objective"] == payload["objective"]
    assert body["question"] == payload["question"]

    listed = client.get("/api/v1/researches")
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert items[0]["id"] == research_id


def test_get_research_by_id(client: TestClient) -> None:
    created = client.post("/api/v1/researches", json={
        "title": "T",
        "objective": "o",
        "question": "q",
        "status": "DRAFT",
    }).json()

    fetched = client.get(f"/api/v1/researches/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "T"


def test_get_unknown_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/researches/{uuid.uuid4()}")
    assert response.status_code == 404


def test_update_research(client: TestClient) -> None:
    created = client.post("/api/v1/researches", json={
        "title": "Antigo",
        "objective": "o",
        "question": "q",
        "status": "DRAFT",
    }).json()

    patched = client.patch(f"/api/v1/researches/{created['id']}", json={
        "title": "Novo",
        "status": "READY",
    })
    assert patched.status_code == 200
    body = patched.json()
    assert body["title"] == "Novo"
    assert body["status"] == "READY"
    assert body["objective"] == "o"
    assert body["question"] == "q"


def test_update_unknown_returns_404(client: TestClient) -> None:
    response = client.patch(f"/api/v1/researches/{uuid.uuid4()}", json={"title": "x"})
    assert response.status_code == 404


def test_delete_research(client: TestClient) -> None:
    created = client.post("/api/v1/researches", json={
        "title": "T",
        "objective": "o",
        "question": "q",
        "status": "DRAFT",
    }).json()

    deleted = client.delete(f"/api/v1/researches/{created['id']}")
    assert deleted.status_code == 204

    assert client.get(f"/api/v1/researches/{created['id']}").status_code == 404
    assert client.get("/api/v1/researches").json() == []


def test_delete_unknown_returns_404(client: TestClient) -> None:
    response = client.delete(f"/api/v1/researches/{uuid.uuid4()}")
    assert response.status_code == 404


def test_create_validation_errors(client: TestClient) -> None:
    assert client.post("/api/v1/researches", json={"title": "no objective"}).status_code == 422
    assert client.post("/api/v1/researches", json={
        "title": "x" * 201,
        "objective": "o",
        "question": "q",
    }).status_code == 422
    assert client.post("/api/v1/researches", json={
        "title": "t",
        "objective": "o",
        "question": "q",
        "status": "ARCHIVED",
    }).status_code == 422


def test_invalid_uuid_returns_422(client: TestClient) -> None:
    assert client.get("/api/v1/researches/not-a-uuid").status_code == 422


def test_pagination_limits_and_offsets(client: TestClient) -> None:
    for i in range(5):
        client.post("/api/v1/researches", json={
            "title": f"R{i}",
            "objective": "o",
            "question": "q",
            "status": "DRAFT",
        })

    page1 = client.get("/api/v1/researches", params={"limit": 2, "offset": 0})
    assert page1.status_code == 200
    assert len(page1.json()) == 2

    page2 = client.get("/api/v1/researches", params={"limit": 2, "offset": 2})
    assert page2.status_code == 200
    assert len(page2.json()) == 2
    ids_page1 = {item["id"] for item in page1.json()}
    ids_page2 = {item["id"] for item in page2.json()}
    assert ids_page1.isdisjoint(ids_page2)
