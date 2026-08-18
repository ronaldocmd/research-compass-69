"""Unit tests for DocumentRepository (RDA-017).

Uses an in-memory SQLite database, same pattern as
tests/test_research_repository.py.
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.document import Document, DocumentStatus
from app.models.research import Research, ResearchStatus
from app.repositories.document_repository import DocumentRepository
from app.repositories.research_repository import ResearchRepository


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory: sessionmaker[Session] = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


@pytest.fixture
def research(db: Session) -> Research:
    return ResearchRepository(db).create(
        title="T", objective="o", question="q", status=ResearchStatus.DRAFT
    )


def make_document_values(research_id: uuid.UUID, **overrides) -> dict:
    values = dict(
        research_id=research_id,
        source="openalex",
        external_id="W1",
        title="Some Title",
        authors=["Ana Silva"],
        publication_year=2022,
        doi="10.1000/xyz",
        url="https://example.org/x",
        abstract="An abstract",
        document_metadata={"type": "article"},
        status=DocumentStatus.PENDING,
    )
    values.update(overrides)
    return values


def test_create_persists_and_returns_document(db: Session, research: Research) -> None:
    repo = DocumentRepository(db)

    document = repo.create(**make_document_values(research.id))

    assert isinstance(document.id, uuid.UUID)
    assert document.research_id == research.id
    assert document.title == "Some Title"
    assert document.authors == ["Ana Silva"]
    assert document.document_metadata == {"type": "article"}
    assert document.status == DocumentStatus.PENDING

    fetched = db.get(Document, document.id)
    assert fetched is not None
    assert fetched.title == "Some Title"


def test_get_by_id_returns_existing_document(db: Session, research: Research) -> None:
    repo = DocumentRepository(db)
    created = repo.create(**make_document_values(research.id))

    result = repo.get_by_id(created.id)

    assert result is not None
    assert result.id == created.id


def test_get_by_id_returns_none_for_unknown_id(db: Session) -> None:
    repo = DocumentRepository(db)

    assert repo.get_by_id(uuid.uuid4()) is None


def test_get_by_research_id_returns_only_documents_of_that_research(
    db: Session, research: Research
) -> None:
    repo = DocumentRepository(db)
    other_research = ResearchRepository(db).create(
        title="Other", objective="o", question="q", status=ResearchStatus.DRAFT
    )
    repo.create(**make_document_values(research.id, title="A"))
    repo.create(**make_document_values(research.id, title="B"))
    repo.create(**make_document_values(other_research.id, title="C"))

    results = repo.get_by_research_id(research.id)

    assert len(results) == 2
    assert {d.title for d in results} == {"A", "B"}


def test_get_by_research_id_supports_pagination(db: Session, research: Research) -> None:
    repo = DocumentRepository(db)
    for i in range(5):
        repo.create(**make_document_values(research.id, title=f"T{i}", external_id=f"W{i}"))

    page = repo.get_by_research_id(research.id, skip=1, limit=2)

    assert len(page) == 2


def test_update_persists_changes(db: Session, research: Research) -> None:
    repo = DocumentRepository(db)
    created = repo.create(**make_document_values(research.id))

    updated = repo.update(created, status=DocumentStatus.DOWNLOADED, title="Novo título")

    assert updated.status == DocumentStatus.DOWNLOADED
    assert updated.title == "Novo título"

    fetched = db.get(Document, created.id)
    assert fetched.status == DocumentStatus.DOWNLOADED
    assert fetched.title == "Novo título"


def test_delete_removes_document(db: Session, research: Research) -> None:
    repo = DocumentRepository(db)
    created = repo.create(**make_document_values(research.id))

    result = repo.delete(created)

    assert result is True
    assert db.get(Document, created.id) is None


def test_bulk_create_persists_multiple_documents(db: Session, research: Research) -> None:
    repo = DocumentRepository(db)
    values = [
        make_document_values(research.id, title="A", external_id="W1"),
        make_document_values(research.id, title="B", external_id="W2"),
        make_document_values(research.id, title="C", external_id="W3"),
    ]

    documents = repo.bulk_create(values)

    assert len(documents) == 3
    assert all(isinstance(d.id, uuid.UUID) for d in documents)
    assert {d.title for d in documents} == {"A", "B", "C"}
    assert len(repo.get_by_research_id(research.id)) == 3


def test_research_document_relationship(db: Session, research: Research) -> None:
    repo = DocumentRepository(db)
    repo.create(**make_document_values(research.id, title="A"))
    repo.create(**make_document_values(research.id, title="B"))

    db.refresh(research)

    assert len(research.documents) == 2
    assert {d.research_id for d in research.documents} == {research.id}


def test_document_research_backref(db: Session, research: Research) -> None:
    repo = DocumentRepository(db)
    created = repo.create(**make_document_values(research.id))

    assert created.research.id == research.id
    assert created.research.title == research.title


def test_cascade_delete_removes_documents_when_research_deleted(
    db: Session, research: Research
) -> None:
    repo = DocumentRepository(db)
    doc_a = repo.create(**make_document_values(research.id, title="A"))
    doc_b = repo.create(**make_document_values(research.id, title="B"))

    ResearchRepository(db).delete(research)

    assert db.get(Document, doc_a.id) is None
    assert db.get(Document, doc_b.id) is None
