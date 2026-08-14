import os
from collections.abc import Generator



import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.main import app

# In-memory SQLite stands in for PostgreSQL: the health repository only runs
# "SELECT 1", so it exercises the API -> Service -> Repository -> DB path.
test_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)


def override_get_db() -> Generator[Session, None, None]:
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def pg_client() -> Generator[TestClient, None, None]:
    """TestClient bound to a real PostgreSQL (TEST_DATABASE_URL), for RDA-006.

    Skipped when no PostgreSQL is reachable, so the suite still runs in
    environments without a database.
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set: PostgreSQL integration tests skipped")

    engine = create_engine(url, future=True)
    PgSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_pg_db() -> Generator[Session, None, None]:
        db = PgSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_pg_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()

