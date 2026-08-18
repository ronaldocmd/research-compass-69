"""Unit tests for DocumentService (RDA-017).

Uses an in-memory SQLite database, same pattern as
tests/test_document_repository.py / tests/test_research_repository.py.
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.document import DocumentStatus
from app.models.research import Research, ResearchStatus
from app.repositories.research_repository import ResearchRepository
from app.schemas.search import NormalizedSearchResult
from app.services.document_service import (
    DocumentNotFoundError,
    DocumentService,
    ResearchNotFoundError,
)


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


def test_save_search_results_persists_documents(db: Session, research: Research) -> None:
    service = DocumentService(db)
    results = [
        NormalizedSearchResult(source="openalex", title="A", external_id="W1"),
        NormalizedSearchResult(source="crossref", title="B", doi="10.1000/xyz"),
    ]

    documents = service.save_search_results(research.id, results)

    assert len(documents) == 2
    assert {d.title for d in documents} == {"A", "B"}
    assert all(d.research_id == research.id for d in documents)


def test_save_search_results_sets_status_pending(db: Session, research: Research) -> None:
    service = DocumentService(db)
    results = [NormalizedSearchResult(source="openalex", title="A")]

    documents = service.save_search_results(research.id, results)

    assert documents[0].status == DocumentStatus.PENDING


def test_save_search_results_converts_all_normalized_fields(
    db: Session, research: Research
) -> None:
    service = DocumentService(db)
    result = NormalizedSearchResult(
        source="openalex",
        title="Deep Learning",
        authors=["Ana Silva"],
        abstract="An abstract",
        publication_year=2022,
        doi="10.1000/xyz",
        url="https://example.org/x",
        external_id="W1",
        metadata={"cited_by_count": 10},
    )

    documents = service.save_search_results(research.id, [result])
    document = documents[0]

    assert document.source == "openalex"
    assert document.title == "Deep Learning"
    assert document.authors == ["Ana Silva"]
    assert document.abstract == "An abstract"
    assert document.publication_year == 2022
    assert document.doi == "10.1000/xyz"
    assert document.url == "https://example.org/x"
    assert document.external_id == "W1"
    assert document.document_metadata == {"cited_by_count": 10}


def test_save_search_results_uses_placeholder_for_missing_title(
    db: Session, research: Research
) -> None:
    service = DocumentService(db)
    result = NormalizedSearchResult(source="openalex")

    documents = service.save_search_results(research.id, [result])

    assert documents[0].title


def test_save_search_results_with_empty_list_returns_empty_list(
    db: Session, research: Research
) -> None:
    service = DocumentService(db)

    assert service.save_search_results(research.id, []) == []


def test_save_search_results_raises_for_unknown_research(db: Session) -> None:
    service = DocumentService(db)
    results = [NormalizedSearchResult(source="openalex", title="A")]

    unknown_id = uuid.uuid4()
    with pytest.raises(ResearchNotFoundError) as exc_info:
        service.save_search_results(unknown_id, results)
    assert exc_info.value.research_id == unknown_id


def test_get_documents_by_research_returns_saved_documents(
    db: Session, research: Research
) -> None:
    service = DocumentService(db)
    service.save_search_results(
        research.id,
        [
            NormalizedSearchResult(source="openalex", title="A"),
            NormalizedSearchResult(source="crossref", title="B"),
        ],
    )

    documents = service.get_documents_by_research(research.id)

    assert len(documents) == 2


def test_get_documents_by_research_raises_for_unknown_research(db: Session) -> None:
    service = DocumentService(db)

    with pytest.raises(ResearchNotFoundError):
        service.get_documents_by_research(uuid.uuid4())


def test_get_documents_by_research_supports_pagination(db: Session, research: Research) -> None:
    service = DocumentService(db)
    service.save_search_results(
        research.id,
        [NormalizedSearchResult(source="openalex", title=f"T{i}") for i in range(5)],
    )

    page = service.get_documents_by_research(research.id, skip=1, limit=2)

    assert len(page) == 2


def test_get_document_returns_existing_document(db: Session, research: Research) -> None:
    service = DocumentService(db)
    [created] = service.save_search_results(
        research.id, [NormalizedSearchResult(source="openalex", title="A")]
    )

    fetched = service.get_document(created.id)

    assert fetched.id == created.id


def test_get_document_raises_for_unknown_id(db: Session) -> None:
    service = DocumentService(db)

    unknown_id = uuid.uuid4()
    with pytest.raises(DocumentNotFoundError) as exc_info:
        service.get_document(unknown_id)
    assert exc_info.value.document_id == unknown_id


def test_update_document_status_persists_new_status(db: Session, research: Research) -> None:
    service = DocumentService(db)
    [created] = service.save_search_results(
        research.id, [NormalizedSearchResult(source="openalex", title="A")]
    )

    updated = service.update_document_status(created.id, DocumentStatus.DOWNLOADED)

    assert updated.status == DocumentStatus.DOWNLOADED
    assert service.get_document(created.id).status == DocumentStatus.DOWNLOADED


def test_update_document_status_raises_for_unknown_id(db: Session) -> None:
    service = DocumentService(db)

    with pytest.raises(DocumentNotFoundError):
        service.update_document_status(uuid.uuid4(), DocumentStatus.FAILED)


def test_bulk_save_of_many_results_at_once(db: Session, research: Research) -> None:
    service = DocumentService(db)
    results = [
        NormalizedSearchResult(source="openalex", title=f"Title {i}", external_id=f"W{i}")
        for i in range(10)
    ]

    documents = service.save_search_results(research.id, results)

    assert len(documents) == 10
    assert len(service.get_documents_by_research(research.id, limit=20)) == 10
