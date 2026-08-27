"""Integration tests for the RDA-052 production wiring.

Exercises the real run path: a persisted research run through the workflow
with fake external services (search/LLM/embedding/download) so no network is
needed, verifying that documents and chunks are persisted and that the status
endpoint reports the same execution the run produced.
"""

import uuid
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints.run import _nodes_factory, _orchestrator
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.chunk import ChunkRecord
from app.models.document import Document, DocumentStatus
from app.models.research import Research
from app.schemas.search import NormalizedSearchResult
from app.services.chunking.schemas import Chunk, ChunkingResult
from app.services.claims.schemas import Claim, ClaimExtractionResult
from app.services.downloader.schemas import DownloadResult
from app.services.embeddings.schemas import EmbeddingResult
from app.services.evidence.schemas import Evidence, EvidenceExtractionResult, EvidenceStatus
from app.services.extraction.schemas import (
    DocumentElement,
    StructuredExtractionResult,
    StructuredPage,
)
from app.services.orchestration.nodes import SynthesisResponse
from app.services.orchestration.orchestrator import ResearchOrchestrator
from app.services.orchestration.wiring import build_research_nodes
from app.services.planning.schemas import PlanTask, ResearchPlan
from app.models.plan import TaskStatus, TaskType

BASE = "/api/v1/researches"


# --- fakes ------------------------------------------------------------------


class FakeSearch:
    def __init__(self, results: list[NormalizedSearchResult]) -> None:
        self._results = results

    def search(self, query: str) -> list[NormalizedSearchResult]:
        return self._results


class FakeDownloader:
    def download(self, url: str) -> DownloadResult:
        return DownloadResult(
            content=b"%PDF-1.4 fake",
            content_type="application/pdf",
            size=12,
            downloaded_at=datetime.now(UTC),
            source_url=url,
        )


class FakeStorage:
    def save(self, document_id, content, metadata) -> str:
        return f"storage/{document_id}.pdf"


class FakeExtractor:
    def extract_structured(self, path, document_id=None) -> StructuredExtractionResult:
        return StructuredExtractionResult(
            document_id=document_id,
            pages=[
                StructuredPage(
                    page_number=1,
                    elements=[
                        DocumentElement(
                            type="paragraph", text="LLMs transformam a pesquisa.", page_number=1, position=0
                        )
                    ],
                )
            ],
            total_pages=1,
            extracted_at=datetime.now(UTC),
        )


class FakeChunker:
    def chunk(self, extraction) -> ChunkingResult:
        chunk = Chunk(
            chunk_id=uuid.uuid4(),
            document_id=extraction.document_id,
            text="LLMs transformam a pesquisa.",
            page_number=1,
            section=None,
            index=0,
            char_count=30,
        )
        return ChunkingResult(
            document_id=extraction.document_id,
            chunks=[chunk],
            total_chunks=1,
            strategy="structure_aware",
            chunked_at=datetime.now(UTC),
        )


class FakeEmbedding:
    def generate_embeddings(self, chunks) -> list[EmbeddingResult]:
        return [
            EmbeddingResult(
                chunk_id=chunk.chunk_id,
                embedding=[0.1, 0.2, 0.3],
                model="fake",
                dimension=3,
                embedded_at=datetime.now(UTC),
                success=True,
            )
            for chunk in chunks
        ]


class FakePlanner:
    def plan(self, plan_input) -> ResearchPlan:
        search_task = PlanTask(
            task_id=uuid.uuid4(),
            title="Buscar literatura sobre LLMs",
            description="Buscar documentos",
            priority=1,
            task_type=TaskType.SEARCH,
            status=TaskStatus.PENDING,
        )
        extract_task = PlanTask(
            task_id=uuid.uuid4(),
            title="Extrair claims sobre LLMs",
            description="Extrair e validar claims",
            priority=2,
            task_type=TaskType.EXTRACT,
            status=TaskStatus.PENDING,
        )
        return ResearchPlan(
            plan_id=uuid.uuid4(),
            research_id=plan_input.research_id,
            tasks=[search_task, extract_task],
            created_at=datetime.now(UTC),
        )


class FakeClaimExtractor:
    def extract(self, chunks, query) -> ClaimExtractionResult:
        chunk = chunks[0]
        claim = Claim(
            claim_id=uuid.uuid4(),
            text="LLMs transformam a pesquisa.",
            chunk_ids=[chunk.chunk_id],
            document_id=chunk.document_id,
            page_number=chunk.page_number,
            extracted_at=datetime.now(UTC),
        )
        return ClaimExtractionResult(
            query=query,
            claims=[claim],
            total_claims=1,
            model_used="fake",
            extracted_at=datetime.now(UTC),
        )


class FakeEvidenceExtractor:
    def extract(self, claim, chunks) -> EvidenceExtractionResult:
        evidence = Evidence(
            evidence_id=uuid.uuid4(),
            claim_id=claim.claim_id,
            text="LLMs transformam a pesquisa.",
            chunk_id=claim.chunk_ids[0],
            document_id=claim.document_id,
            page_number=claim.page_number,
            status=EvidenceStatus.SUPPORTED,
            extracted_at=datetime.now(UTC),
        )
        return EvidenceExtractionResult(
            claim_id=claim.claim_id,
            evidence=[evidence],
            final_status=EvidenceStatus.SUPPORTED,
            extracted_at=datetime.now(UTC),
        )


class FakeLLM:
    def complete(self, prompt, response_model):
        return SynthesisResponse(summary="Resumo consolidado da pesquisa.")


class FakeRetriever:
    def __init__(self) -> None:
        self._chunk_id = uuid.uuid4()
        self._document_id = uuid.uuid4()

    def retrieve(self, query):
        from app.services.retrieval.schemas import RetrievedChunk, RetrievalResult

        return RetrievalResult(
            query=query,
            chunks=[
                RetrievedChunk(
                    chunk_id=self._chunk_id,
                    document_id=self._document_id,
                    text="LLMs transformam a pesquisa.",
                    page_number=1,
                    section=None,
                    score=0.9,
                    document_title="LLMs na pesquisa",
                )
            ],
            total_found=1,
            retrieved_at=datetime.now(UTC),
        )


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory: sessionmaker[Session] = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    def override_get_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def _create_research(client: TestClient) -> uuid.UUID:
    response = client.post(
        BASE,
        json={
            "title": "Impacto de LLMs",
            "objective": "Mapear literatura",
            "question": "Qual o estado da arte?",
        },
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def _search_result(title: str, doi: str) -> NormalizedSearchResult:
    return NormalizedSearchResult(
        source="openalex",
        title=title,
        authors=["Autor A"],
        abstract="Resumo.",
        publication_year=2024,
        doi=doi,
        url=f"https://example.org/{doi}",
        external_id=doi,
    )


# --- tests ------------------------------------------------------------------


def test_run_persists_documents_chunks_and_summary(client: TestClient) -> None:
    research_id = _create_research(client)
    result = _search_result("LLMs na pesquisa", "10.1000/llm")
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        def fake_nodes_factory():
            def build(session, rid):
                return build_research_nodes(
                    session,
                    rid,
                    search_service=FakeSearch([result]),
                    downloader=FakeDownloader(),
                    storage=FakeStorage(),
                    extractor=FakeExtractor(),
                    chunker=FakeChunker(),
                    embedding_service=FakeEmbedding(),
                    planner=FakePlanner(),
                    claim_extractor=FakeClaimExtractor(),
                    evidence_extractor=FakeEvidenceExtractor(),
                    llm=FakeLLM(),
                    retriever=FakeRetriever(),
                )

            return build

        app.dependency_overrides[_nodes_factory] = fake_nodes_factory

        run_resp = client.post(f"{BASE}/{research_id}/run")
        assert run_resp.status_code == 200, run_resp.text
        body = run_resp.json()
        assert body["current_stage"] == "COMPLETED"
        assert len(body["claims"]) == 1
        assert len(body["evidence_items"]) == 1

        # Status reports the same execution (C2 fix).
        status_resp = client.get(f"{BASE}/{research_id}/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["execution_id"] == body["execution_id"]

        # Documents and chunks were persisted.
        docs = db.execute(select(Document)).scalars().all()
        assert len(docs) == 1
        assert docs[0].title == "LLMs na pesquisa"
        assert docs[0].status == DocumentStatus.PROCESSED
        chunks = db.execute(select(ChunkRecord)).scalars().all()
        assert len(chunks) == 1
        assert chunks[0].document_id == docs[0].id
        research = db.get(Research, research_id)
        assert research.summary == "Resumo consolidado da pesquisa."
    finally:
        gen.close()


def test_run_without_persisted_research_returns_404(client: TestClient) -> None:
    # A non-existent research must not fabricate a COMPLETED state (RDA-056).
    orchestrator = ResearchOrchestrator()
    app.dependency_overrides[_orchestrator] = lambda: orchestrator
    research_id = uuid.uuid4()

    run_resp = client.post(f"{BASE}/{research_id}/run")
    assert run_resp.status_code == 404
