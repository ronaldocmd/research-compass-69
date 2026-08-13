from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.main import app
from app.repositories.health_repository import HealthRepository


def test_liveness_does_not_require_database() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == settings.VERSION


def test_api_v1_health_reports_database_up(client: TestClient) -> None:
    response = client.get(f"{settings.API_V1_PREFIX}/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "up",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }


def test_api_v1_health_reports_database_down(client: TestClient, monkeypatch) -> None:
    def broken_execute(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(HealthRepository, "ping", lambda self: broken_execute(self))
    response = client.get(f"{settings.API_V1_PREFIX}/health")
    assert response.status_code == 500


def test_api_v1_health_degraded_when_ping_fails(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(HealthRepository, "ping", lambda self: False)
    response = client.get(f"{settings.API_V1_PREFIX}/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "down"


def test_cors_headers_present(client: TestClient) -> None:
    origin = settings.cors_origins_list[0]
    response = client.get("/health", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin


def test_openapi_exposes_only_health_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths) == {"/health", f"{settings.API_V1_PREFIX}/health"}
