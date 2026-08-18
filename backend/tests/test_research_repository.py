"""Unit tests for ResearchRepository (RDA-006).

Uses an in-memory SQLite database to exercise the real SQLAlchemy queries
without requiring PostgreSQL.
"""

import time
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.research import Research, ResearchStatus
from app.repositories.research_repository import ResearchRepository


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=[Base.metadata.tables["researches"]])
    factory: sessionmaker[Session] = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def test_create_persists_and_returns_research(db: Session) -> None:
    repo = ResearchRepository(db)
    payload = {
        "title": "Novo título",
        "objective": "Objetivo",
        "question": "Pergunta",
        "status": ResearchStatus.DRAFT,
    }

    result = repo.create(**payload)

    assert isinstance(result.id, uuid.UUID)
    assert result.title == payload["title"]
    assert result.objective == payload["objective"]
    assert result.question == payload["question"]
    assert result.status == ResearchStatus.DRAFT
    assert isinstance(result.created_at, datetime)
    assert isinstance(result.updated_at, datetime)

    fetched = db.get(Research, result.id)
    assert fetched is not None
    assert fetched.title == payload["title"]


def test_list_returns_ordered_researches(db: Session) -> None:
    repo = ResearchRepository(db)
    first = repo.create(title="A", objective="o", question="q", status=ResearchStatus.DRAFT)
    time.sleep(1)
    second = repo.create(title="B", objective="o", question="q", status=ResearchStatus.READY)

    results = repo.list(limit=10, offset=0)

    assert [r.title for r in results] == ["B", "A"]
    assert results[0].id == second.id
    assert results[1].id == first.id


def test_list_supports_pagination(db: Session) -> None:
    repo = ResearchRepository(db)
    for i in range(5):
        repo.create(title=f"T{i}", objective="o", question="q", status=ResearchStatus.DRAFT)
        time.sleep(1)

    page = repo.list(limit=2, offset=1)
    assert len(page) == 2
    assert [r.title for r in page] == ["T3", "T2"]


def test_get_returns_existing_research(db: Session) -> None:
    repo = ResearchRepository(db)
    created = repo.create(title="T", objective="o", question="q", status=ResearchStatus.DRAFT)

    result = repo.get(created.id)

    assert result is not None
    assert result.id == created.id
    assert result.title == "T"


def test_get_returns_none_for_unknown_id(db: Session) -> None:
    repo = ResearchRepository(db)

    assert repo.get(uuid.uuid4()) is None


def test_update_persists_changes(db: Session) -> None:
    repo = ResearchRepository(db)
    created = repo.create(title="Antigo", objective="o", question="q", status=ResearchStatus.DRAFT)
    original_updated_at = created.updated_at

    updated = repo.update(created, title="Novo", status=ResearchStatus.READY)

    assert updated.title == "Novo"
    assert updated.status == ResearchStatus.READY
    assert updated.id == created.id
    assert updated.objective == "o"
    assert updated.question == "q"
    # updated_at should change after update
    assert updated.updated_at >= original_updated_at

    fetched = db.get(Research, created.id)
    assert fetched.title == "Novo"
    assert fetched.status == ResearchStatus.READY


def test_delete_removes_research(db: Session) -> None:
    repo = ResearchRepository(db)
    created = repo.create(title="T", objective="o", question="q", status=ResearchStatus.DRAFT)

    repo.delete(created)

    assert db.get(Research, created.id) is None
