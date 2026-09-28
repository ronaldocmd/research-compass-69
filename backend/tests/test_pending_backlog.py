"""RDA-067: score persistence and the pending-document backlog batch.

A single orchestration run only processes ``max_documents`` of what a broad
multi-source search returns (RDA-066); everything else is persisted as
"pending" and, before this, never revisited. These tests cover the two
pieces that make the backlog usable: writing the selection-time relevance
score onto the Document row (``record_relevance_score``), and working the
backlog off in ranked batches (``process_pending_documents``).
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.document import Document, DocumentStatus
from app.repositories.research_repository import ResearchRepository
from app.services.orchestration.wiring import ProcessResult, WorkflowServices

NOW = datetime.now(UTC)


class _FakeEmbeddingProvider:
    """Deterministic 2D embedding: cosine sim is high for "rare earth" text,
    low otherwise, mirroring the fake used in test_nodes.py."""

    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0] if "rare earth" in text.lower() else [0.0, 1.0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class _BrokenEmbeddingProvider:
    def embed(self, text: str) -> list[float]:
        raise RuntimeError("embedding backend unreachable")


@pytest.fixture
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, future=True)() as db:
        yield db


def _seed_research(db, question="What is the outlook for rare earth mining?"):
    return ResearchRepository(db).create(title="t", objective="o", question=question)


def _pending_doc(db, research_id, *, title, abstract="", score=None):
    doc = Document(
        id=uuid.uuid4(), research_id=research_id, source="openalex", title=title,
        abstract=abstract, doi=f"10.1/{uuid.uuid4().hex[:8]}", authors=[],
        document_metadata={}, status=DocumentStatus.PENDING, relevance_score=score,
    )
    db.add(doc)
    db.flush()
    return doc


def _services(db, research_id, **overrides) -> WorkflowServices:
    fake = object()
    defaults = dict(
        downloader=fake, storage=fake, extractor=fake, chunker=fake,
        planner=fake, claim_extractor=fake, evidence_extractor=fake, llm=fake,
        retriever=fake, validator=fake, provenance_resolver=fake, confidence_scorer=fake,
    )
    defaults.update(overrides)
    return WorkflowServices(db, research_id, **defaults)


# --- record_relevance_score ---------------------------------------------------


def test_record_relevance_score_persists_onto_document(db_session) -> None:
    research = _seed_research(db_session)
    doc = _pending_doc(db_session, research.id, title="Rare earth outlook", abstract="")
    db_session.commit()
    services = _services(db_session, research.id)

    from app.services.orchestration.wiring import _selection_id_from_document

    services.record_relevance_score(_selection_id_from_document(doc), 0.87)

    db_session.refresh(doc)
    assert doc.relevance_score == pytest.approx(0.87)


def test_record_relevance_score_unknown_id_is_a_noop(db_session) -> None:
    research = _seed_research(db_session)
    services = _services(db_session, research.id)
    services.record_relevance_score(uuid.uuid4(), 0.5)  # must not raise


# --- process_pending_documents -------------------------------------------------


def test_process_pending_documents_scores_unscored_backlog(db_session) -> None:
    research = _seed_research(db_session)
    on_topic = _pending_doc(db_session, research.id, title="Rare earth supply chains")
    off_topic = _pending_doc(db_session, research.id, title="Cooking recipes for beginners")
    db_session.commit()

    services = _services(
        db_session, research.id, embedding_service=_Provider(_FakeEmbeddingProvider()),
    )
    services.process = lambda doc_id: ProcessResult(chunk_ids=[uuid.uuid4()])

    stats = services.process_pending_documents(batch_size=10)

    db_session.refresh(on_topic)
    db_session.refresh(off_topic)
    assert stats["newly_scored"] == 2
    assert on_topic.relevance_score == pytest.approx(1.0)
    assert off_topic.relevance_score == pytest.approx(0.0)


def test_process_pending_documents_processes_best_score_first(db_session) -> None:
    research = _seed_research(db_session)
    # Pre-scored so no embedding call is needed to rank them.
    low = _pending_doc(db_session, research.id, title="Low fit", score=0.1)
    high = _pending_doc(db_session, research.id, title="High fit", score=0.9)
    medium = _pending_doc(db_session, research.id, title="Medium fit", score=0.5)
    db_session.commit()

    services = _services(db_session, research.id)
    calls: list[uuid.UUID] = []
    services.process = lambda doc_id: (calls.append(doc_id), ProcessResult(chunk_ids=[uuid.uuid4()]))[1]

    stats = services.process_pending_documents(batch_size=2)

    from app.services.orchestration.wiring import _selection_id_from_document

    assert calls == [
        _selection_id_from_document(high), _selection_id_from_document(medium),
    ]
    assert stats["selected"] == 2
    assert stats["processed"] == 2
    assert stats["remaining_pending"] == 1


def test_process_pending_documents_counts_failures(db_session) -> None:
    research = _seed_research(db_session)
    _pending_doc(db_session, research.id, title="Doc A", score=0.9)
    db_session.commit()

    services = _services(db_session, research.id)
    services.process = lambda doc_id: ProcessResult(reason="download_failed: boom")

    stats = services.process_pending_documents(batch_size=10)

    assert stats["processed"] == 0
    assert stats["failed"] == 1


def test_process_pending_documents_degrades_when_embedding_backend_down(db_session) -> None:
    """A temporarily unreachable embedding backend must not block the
    backlog: unscored documents are still processed, just in existing
    (oldest-first) order instead of ranked order."""
    research = _seed_research(db_session)
    doc = _pending_doc(db_session, research.id, title="Unscorable doc")
    db_session.commit()

    services = _services(
        db_session, research.id, embedding_service=_Provider(_BrokenEmbeddingProvider()),
    )
    services.process = lambda doc_id: ProcessResult(chunk_ids=[uuid.uuid4()])

    stats = services.process_pending_documents(batch_size=10)

    assert stats["newly_scored"] == 0
    assert stats["processed"] == 1
    db_session.refresh(doc)
    assert doc.relevance_score is None


def test_process_pending_documents_empty_backlog_is_a_noop(db_session) -> None:
    research = _seed_research(db_session)
    services = _services(db_session, research.id)

    stats = services.process_pending_documents()

    assert stats == {
        "newly_scored": 0, "selected": 0, "processed": 0, "failed": 0,
        "remaining_pending": 0,
    }


class _Provider:
    """Minimal stand-in for EmbeddingService exposing just ``.provider``."""

    def __init__(self, provider) -> None:
        self.provider = provider
