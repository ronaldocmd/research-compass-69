"""Integration-style checks for the SQLAlchemy layer (no domain models).

These tests never require PostgreSQL: they validate the engine/session
factory wiring and the repository SQL path. When `TEST_DATABASE_URL` points
to a live PostgreSQL instance, a real connection test also runs.
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_engine, get_sessionmaker
from app.repositories.health_repository import HealthRepository


def test_database_url_comes_from_settings_not_hardcoded() -> None:
    assert settings.DATABASE_URL.startswith("postgresql+psycopg://")


def test_engine_is_lazy_and_cached() -> None:
    assert get_engine() is get_engine()
    assert get_sessionmaker() is get_sessionmaker()


def test_declarative_base_metadata_is_available() -> None:
    # RDA-031 stage: Research, Document, Chunk, ResearchPlan and PlanTask are
    # the registered domain tables. RDA-049 adds human_evaluations; RDA-050
    # adds usage_events.
    assert set(Base.metadata.tables) == {
        "researches",
        "documents",
        "chunks",
        "research_plans",
        "plan_tasks",
        "workflow_checkpoints",
        "human_evaluations",
        "usage_events",
    }


def test_repository_ping_uses_a_real_session() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    factory: sessionmaker[Session] = sessionmaker(bind=engine, future=True)
    with factory() as db:
        assert HealthRepository(db).ping() is True


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set (no live PostgreSQL available)",
)
def test_live_postgres_connection() -> None:
    engine = create_engine(os.environ["TEST_DATABASE_URL"], future=True)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1
        assert "PostgreSQL" in conn.execute(text("SELECT version()")).scalar_one()
