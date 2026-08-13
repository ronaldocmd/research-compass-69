"""Tests for the Research model (RDA-005).

Model-level tests run without a database. Persistence/round-trip tests run
against a real PostgreSQL when `TEST_DATABASE_URL` is set (opt-in), because
the model relies on PostgreSQL UUID and native enum types.
"""
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import String, create_engine, inspect, text
from sqlalchemy.exc import DataError, IntegrityError, StatementError
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Research, ResearchStatus

PG_URL = os.getenv("TEST_DATABASE_URL")
requires_pg = pytest.mark.skipif(
    not PG_URL, reason="TEST_DATABASE_URL not set (no live PostgreSQL available)"
)


def test_status_enum_has_only_draft_and_ready() -> None:
    assert [s.value for s in ResearchStatus] == ["DRAFT", "READY"]


def test_model_registered_on_metadata() -> None:
    assert "researches" in Base.metadata.tables


def test_column_definitions() -> None:
    table = Base.metadata.tables["researches"]
    assert set(table.c.keys()) == {
        "id",
        "title",
        "objective",
        "question",
        "status",
        "created_at",
        "updated_at",
    }
    assert table.c.id.primary_key
    assert isinstance(table.c.title.type, String)
    assert table.c.title.type.length == 200
    for name in ("title", "objective", "question", "status", "created_at", "updated_at"):
        assert table.c[name].nullable is False
    assert table.c.status.type.enums == ["DRAFT", "READY"]
    assert table.c.created_at.type.timezone is True
    assert table.c.updated_at.type.timezone is True


def test_python_side_defaults() -> None:
    table = Base.metadata.tables["researches"]
    assert table.c.id.default.arg is uuid.uuid4
    assert table.c.status.default.arg is ResearchStatus.DRAFT
    assert table.c.updated_at.onupdate is not None


@pytest.fixture
def pg_session() -> Session:
    engine = create_engine(PG_URL, future=True)
    with engine.begin() as conn:
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
    Base.metadata.create_all(engine, tables=[Base.metadata.tables["researches"]])
    factory: sessionmaker[Session] = sessionmaker(bind=engine, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(engine, tables=[Base.metadata.tables["researches"]])
        ResearchStatus  # keep import used
        with engine.begin() as conn:
            conn.execute(text("DROP TYPE IF EXISTS research_status"))
        engine.dispose()


@requires_pg
def test_create_valid_research_generates_uuid_and_timestamps(pg_session: Session) -> None:
    r = Research(title="Impacto de LLMs", objective="Mapear literatura", question="Qual o estado da arte?")
    pg_session.add(r)
    pg_session.commit()
    pg_session.refresh(r)

    assert isinstance(r.id, uuid.UUID)
    assert r.status is ResearchStatus.DRAFT
    assert isinstance(r.created_at, datetime) and r.created_at.tzinfo is not None
    assert isinstance(r.updated_at, datetime)
    assert r.created_at <= datetime.now(timezone.utc)


@requires_pg
def test_round_trip_and_allowed_status_values(pg_session: Session) -> None:
    ids = []
    for status in ResearchStatus:
        r = Research(title=f"T {status.value}", objective="obj", question="q", status=status)
        pg_session.add(r)
        ids.append(r)
    pg_session.commit()

    for r in ids:
        fetched = pg_session.get(Research, r.id)
        assert fetched is not None
        assert fetched.status in {ResearchStatus.DRAFT, ResearchStatus.READY}


@requires_pg
def test_updated_at_changes_on_update(pg_session: Session) -> None:
    r = Research(title="Antes", objective="obj", question="q")
    pg_session.add(r)
    pg_session.commit()
    before = r.updated_at

    r.title = "Depois"
    pg_session.commit()
    pg_session.refresh(r)
    assert r.updated_at >= before
    assert r.title == "Depois"


@requires_pg
def test_required_fields_are_enforced(pg_session: Session) -> None:
    pg_session.add(Research(title="Sem objetivo", question="q"))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


@requires_pg
def test_title_length_limit_is_enforced(pg_session: Session) -> None:
    pg_session.add(Research(title="x" * 201, objective="obj", question="q"))
    with pytest.raises(DataError):
        pg_session.commit()
    pg_session.rollback()


@requires_pg
def test_invalid_status_is_rejected(pg_session: Session) -> None:
    pg_session.add(Research(title="Ruim", objective="obj", question="q", status="ARCHIVED"))
    with pytest.raises((StatementError, IntegrityError, DataError)):
        pg_session.commit()
    pg_session.rollback()


@requires_pg
def test_database_schema_matches_model(pg_session: Session) -> None:
    insp = inspect(pg_session.get_bind())
    cols = {c["name"]: c for c in insp.get_columns("researches")}
    assert set(cols) == {
        "id",
        "title",
        "objective",
        "question",
        "status",
        "created_at",
        "updated_at",
    }
    assert insp.get_pk_constraint("researches")["constrained_columns"] == ["id"]
