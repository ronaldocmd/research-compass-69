"""Production wiring for the research workflow (RDA-052).

Connects the services built across RDA-011..RDA-031 to the workflow nodes
(RDA-034) so a real research can traverse the full pipeline. This module is
the single place that assembles the real services and the thin adapters that
bridge each service's contract to what the nodes expect.

It deliberately does NOT reimplement any service: it only wires existing
components and adapts their signatures to the node contracts.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from sqlalchemy import select

from app.models.chunk import ChunkRecord
from app.models.document import Document, DocumentStatus
from app.models.evidence_chain import ClaimRecord, ConfidenceRecord, ValidationRecord
from app.models.plan import PlanTaskRecord, ResearchPlanRecord, TaskType
from app.core.config import settings
from app.repositories.evidence_chain_repository import EvidenceChainRepository
from app.services.claims.schemas import Claim
from app.services.confidence.schemas import ConfidenceLevel
from app.services.validation.schemas import ValidationStatus
from app.services.claims.extractor import ClaimExtractor
from app.services.chunking.chunker import DocumentChunker
from app.services.confidence.scorer import ConfidenceScorer
from app.services.document_service import DocumentNotFoundError, DocumentService
from app.services.downloader.downloader import DocumentDownloader
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.evidence.extractor import EvidenceExtractor
from app.services.extraction.pdf_extractor import PDFExtractor
from app.services.llm.openai_provider import OpenAILLMProvider
from app.services.orchestration.nodes import ResearchNodes
from app.services.planning.planner import ResearchPlanner
from app.services.provenance.resolver import ProvenanceResolver
from app.services.provenance.schemas import DocumentSource
from app.services.research_plan_service import ResearchPlanService
from app.services.research_service import ResearchService
from app.services.retrieval.retriever import DocumentRetriever, cosine_similarity
from app.services.retrieval.schemas import IndexedChunk
from app.services.search.search_service import SearchService
from app.services.storage.storage import FileStorage
from app.services.validation.validator import EvidenceValidator
from app.services.workflow.state import ResearchWorkflowState

# Same fixed namespace used by ResearchNodes.selection_node so the
# deterministic selection UUIDs match the persisted Documents.
_SELECTION_NAMESPACE = uuid.UUID("8f1c2a3e-4b5d-4e6f-9a7b-0c1d2e3f4a5b")


def _selection_id_from_document(document: Document) -> uuid.UUID:
    key = document.doi or document.external_id or document.title or document.source or ""
    return uuid.uuid5(_SELECTION_NAMESPACE, key)


@dataclass
class ProcessResult:
    """Outcome of processing one document (RDA-058).

    Carries the produced chunk ids plus a reason when the document could not
    be processed, so the pipeline can distinguish a document dropped for
    technical unavailability (e.g. no URL, HTML-only, download/extraction
    failure) from one that was processed. This makes downloadability
    observable instead of silently conflating it with relevance.
    """

    chunk_ids: list[uuid.UUID] = field(default_factory=list)
    reason: str | None = None


class WorkflowServices:
    """Assembles the real services and exposes node-compatible adapters.

    Every service can be injected (defaulting to the real implementation) so
    tests can substitute fakes without network access.
    """

    def __init__(
        self,
        db: Session,
        research_id: uuid.UUID,
        *,
        search_service: SearchService | None = None,
        downloader: DocumentDownloader | None = None,
        storage: FileStorage | None = None,
        extractor: PDFExtractor | None = None,
        chunker: DocumentChunker | None = None,
        embedding_service: EmbeddingService | None = None,
        planner: ResearchPlanner | None = None,
        claim_extractor: ClaimExtractor | None = None,
        evidence_extractor: EvidenceExtractor | None = None,
        llm: OpenAILLMProvider | None = None,
        retriever: DocumentRetriever | None = None,
        validator: EvidenceValidator | None = None,
        provenance_resolver: ProvenanceResolver | None = None,
        confidence_scorer: ConfidenceScorer | None = None,
    ) -> None:
        self.db = db
        self.research_id = research_id

        self.document_service = DocumentService(db)
        self.research_service = ResearchService(db)
        self.search_service = search_service or SearchService()
        self.downloader = downloader or DocumentDownloader()
        self.storage = storage or FileStorage()
        self.extractor = extractor or PDFExtractor()
        self.chunker = chunker or DocumentChunker()
        self.embedding_service = embedding_service or EmbeddingService()
        self.planner = planner or ResearchPlanner()
        self.claim_extractor = claim_extractor or ClaimExtractor()
        self.evidence_extractor = evidence_extractor or EvidenceExtractor()
        self.llm = llm or OpenAILLMProvider()
        # Epistemological chain (RDA-061): the orphan services are wired here
        # so the validation node can validate, resolve provenance and score
        # confidence, then persist the chain.
        self.validator = validator or EvidenceValidator()
        self.provenance_resolver = provenance_resolver or ProvenanceResolver()
        self.confidence_scorer = confidence_scorer or ConfidenceScorer()
        self._evidence_chain_repo = EvidenceChainRepository(db)
        self._plan_service = ResearchPlanService(db, planner=self.planner)

        # Shared, mutable retrieval index: the retriever reads it and the
        # processor appends to it as documents are embedded.
        self._index: list[IndexedChunk] = []
        self.retriever = retriever or DocumentRetriever(index=self._index)
        self._load_prior_index()

        # selection UUID -> persisted Document, built as search results are
        # persisted so the processor can resolve the node's deterministic id.
        self._doc_by_selection_id: dict[uuid.UUID, Document] = {}

    # --- node adapters -------------------------------------------------------

    def research_loader(self, research_id: uuid.UUID) -> Document | None:
        try:
            return self.research_service.get(research_id)
        except Exception:
            return None

    def search(self, query: str) -> list:
        # Query every enabled source in parallel (RDA-066). Custom services
        # that only expose ``search`` (single provider) are still supported.
        search = getattr(self.search_service, "search_all", self.search_service.search)
        results = search(query)
        # Only NEW documents go on to selection/processing: results already
        # collected in earlier rounds must not use up the document slots or
        # be downloaded and embedded again.
        return self._persist_results(results)

    def record_relevance_score(self, doc_id: uuid.UUID, score: float) -> None:
        """Persist the selection-time relevance score onto its Document row.

        Best-effort: the score computed in ``selection_node`` (RDA-058) was
        previously discarded after being used once to filter, leaving
        ``Document.relevance_score`` NULL for everything and every
        non-selected "pending" Document unrankable (RDA-067). Writing it
        back here lets a later batch (``process_pending_documents``) order
        the backlog by fit instead of arbitrary insertion order, and gives
        operators visibility into why a document was or wasn't selected.
        """
        document = self._doc_by_selection_id.get(doc_id) or self._find_document(doc_id)
        if document is None:
            return
        self.document_service.repository.update(document, relevance_score=score)

    def process_pending_documents(self, *, batch_size: int | None = None) -> dict:
        """Score, rank and work off this research's PENDING backlog (RDA-067).

        A single orchestration run only ever processes ``max_documents``
        (the selection cap, RDA-034) of what a broad multi-source search
        returns (RDA-066) — everything else is persisted as "pending" and,
        until now, never revisited unless the user reran search from
        scratch. This spends additional processing budget on documents
        already collected, ranked by fit to the research question rather
        than arbitrary insertion order, without paying for new search calls
        or risking duplicate documents (``search()`` already de-duplicates
        by doi/title on the way in).

        Any pending document lacking a ``relevance_score`` (backlog
        collected before RDA-067, or selection ran without a question/
        embedding provider) is scored first, against the same
        title+abstract text and cosine-similarity method ``selection_node``
        uses, so later calls keep working the backlog top-down. Scoring
        failures degrade to processing in existing order rather than
        raising, since a temporarily unreachable embedding backend must
        never block the backlog from being worked at all.
        """
        batch_size = batch_size if batch_size is not None else settings.PENDING_BATCH_DEFAULT_SIZE
        stats = {"newly_scored": 0, "selected": 0, "processed": 0, "failed": 0}

        pending = self.document_service.repository.get_pending_by_research(
            self.research_id, limit=10_000
        )
        unscored = [d for d in pending if d.relevance_score is None]
        if unscored:
            stats["newly_scored"] = self._score_pending(unscored)
            if stats["newly_scored"]:
                pending = self.document_service.repository.get_pending_by_research(
                    self.research_id, limit=10_000
                )

        batch = pending[:batch_size]
        stats["selected"] = len(batch)
        for document in batch:
            result = self.process(_selection_id_from_document(document))
            if getattr(result, "reason", None):
                stats["failed"] += 1
            else:
                stats["processed"] += 1

        stats["remaining_pending"] = len(pending) - len(batch)
        return stats

    def _score_pending(self, documents: list[Document]) -> int:
        """Compute and persist relevance_score for ``documents``; returns how many.

        Embeds in EMBEDDING_BATCH_SIZE-sized chunks (a backlog can be in the
        hundreds, and one request per document would be slow while one
        request for all of them risks the backend's request-size/timeout
        limits); one chunk failing does not lose the rest.
        """
        research = self.research_service.get(self.research_id)
        if research is None or not research.question:
            return 0
        provider = self.embedding_service.provider
        try:
            query_embedding = provider.embed(research.question)
        except Exception:
            return 0

        texts = [
            " ".join(part for part in (d.title, d.abstract) if part).strip()
            for d in documents
        ]
        indexed = [(i, t) for i, t in enumerate(texts) if t]
        if not indexed:
            return 0

        embed_batch = getattr(provider, "embed_batch", None)
        chunk_size = max(1, settings.EMBEDDING_BATCH_SIZE)
        scored = 0
        for start in range(0, len(indexed), chunk_size):
            chunk = indexed[start : start + chunk_size]
            try:
                if embed_batch is not None:
                    vectors = embed_batch([t for _, t in chunk])
                else:
                    vectors = [provider.embed(t) for _, t in chunk]
            except Exception:
                continue  # this chunk's scores are lost; later chunks still try
            if len(vectors) != len(chunk):
                continue
            for (i, _), vector in zip(chunk, vectors):
                try:
                    score = cosine_similarity(query_embedding, vector)
                except Exception:
                    continue
                self.document_service.repository.update(documents[i], relevance_score=score)
                scored += 1
        return scored

    def process(self, doc_id: uuid.UUID) -> ProcessResult:
        """Download, extract, chunk, embed and persist one document.

        Returns a ProcessResult with the produced chunk UUIDs and, when the
        document cannot be processed, a ``reason`` describing why (RDA-058).
        """
        document = self._doc_by_selection_id.get(doc_id)
        if document is None:
            document = self._find_document(doc_id)
        if document is None:
            return ProcessResult(reason="document_not_found")
        if not document.url:
            return ProcessResult(reason="no_url")

        try:
            download = self.downloader.download(document.url)
        except Exception as exc:
            self.document_service.repository.update(
                document, status=DocumentStatus.FAILED
            )
            return ProcessResult(reason=f"download_failed: {exc}")

        try:
            storage_path = self.storage.save(
                document.id,
                download.content,
                {"content_type": download.content_type},
            )
        except Exception as exc:
            self.document_service.repository.update(
                document, status=DocumentStatus.FAILED
            )
            return ProcessResult(reason=f"storage_rejected: {exc}")

        self.document_service.repository.update(
            document,
            storage_path=storage_path,
            file_size=download.size,
            status=DocumentStatus.DOWNLOADED,
        )

        try:
            extraction = self.extractor.extract_structured(
                storage_path, document_id=document.id
            )
        except Exception as exc:
            self.document_service.repository.update(
                document, status=DocumentStatus.FAILED
            )
            return ProcessResult(reason=f"extraction_failed: {exc}")

        chunking = self.chunker.chunk(extraction)
        embeddings = self.embedding_service.generate_embeddings(chunking.chunks)

        chunk_ids: list[uuid.UUID] = []
        try:
            for chunk, embedding in zip(chunking.chunks, embeddings):
                if not embedding.success or embedding.embedding is None:
                    continue
                self.db.add(
                    ChunkRecord(
                        chunk_id=chunk.chunk_id,
                        document_id=document.id,
                        chunk_index=chunk.index,
                        text=chunk.text,
                        page_number=chunk.page_number,
                        section=chunk.section,
                        char_count=chunk.char_count,
                        embedding=embedding.embedding,
                        embedding_model=embedding.model,
                        embedding_dimension=embedding.dimension,
                        embedded_at=embedding.embedded_at,
                    )
                )
                chunk_ids.append(chunk.chunk_id)
            self.db.commit()
        except Exception as exc:
            # A failed flush leaves the shared session unusable; roll back so
            # the remaining documents can still be processed.
            self.db.rollback()
            self.document_service.repository.update(
                document, status=DocumentStatus.FAILED
            )
            return ProcessResult(reason=f"persist_failed: {exc}")

        # Index only after the chunks are safely committed.
        indexed = set(chunk_ids)
        for chunk, embedding in zip(chunking.chunks, embeddings):
            if chunk.chunk_id in indexed:
                self._index.append(
                    IndexedChunk(
                        chunk_id=chunk.chunk_id,
                        document_id=document.id,
                        text=chunk.text,
                        page_number=chunk.page_number,
                        section=chunk.section,
                        embedding=embedding.embedding,
                        document_title=document.title,
                    )
                )
        if not chunk_ids:
            self.document_service.repository.update(
                document, status=DocumentStatus.FAILED
            )
            return ProcessResult(reason="no_chunks_embedded")
        self.document_service.repository.update(
            document, status=DocumentStatus.PROCESSED
        )
        return ProcessResult(chunk_ids=chunk_ids)

    def save_summary(self, research_id: uuid.UUID, summary: str) -> None:
        try:
            research = self.research_service.get(research_id)
        except Exception:
            return
        self.research_service.repository.update(research, summary=summary)

    def resolve_document_source(
        self, document_id: uuid.UUID, chunk
    ) -> DocumentSource | None:
        """Resolve the original-source metadata for a chunk (RDA-061).

        Returns None when the document is not found, so the validation node
        simply skips provenance for that chunk instead of failing.
        """
        try:
            document = self.document_service.get_document(document_id)
        except DocumentNotFoundError:
            return None
        return DocumentSource(
            document_id=document.id,
            title=document.title,
            url=document.url,
            doi=document.doi,
            page_number=chunk.page_number,
            chunk_id=chunk.chunk_id,
        )

    # --- deepening rounds ----------------------------------------------------

    def _load_prior_index(self) -> None:
        """Seed the retrieval index with chunks from earlier rounds.

        Chunks already cited by a claim are skipped: retrieving them again
        would only re-extract the same claims. What remains is material that
        earlier rounds embedded but never mined, which the new query can reach.
        """
        try:
            claimed: set[str] = set()
            for chunk_ids in self.db.scalars(
                select(ClaimRecord.chunk_ids).where(
                    ClaimRecord.research_id == self.research_id
                )
            ):
                claimed.update(str(c) for c in (chunk_ids or []))
            rows = self.db.execute(
                select(ChunkRecord, Document.title)
                .join(Document, Document.id == ChunkRecord.document_id)
                .where(
                    Document.research_id == self.research_id,
                    ChunkRecord.embedding.is_not(None),
                )
            ).all()
        except Exception:
            # Best-effort: never block a run because history could not be read.
            self.db.rollback()
            return
        for record, title in rows:
            if str(record.chunk_id) in claimed:
                continue
            self._index.append(
                IndexedChunk(
                    chunk_id=record.chunk_id,
                    document_id=record.document_id,
                    text=record.text,
                    page_number=record.page_number,
                    section=record.section,
                    embedding=record.embedding,
                    document_title=title,
                )
            )

    def load_history(self, research_id: uuid.UUID) -> tuple[list[str], list[str]]:
        """Return (previous search queries, titles already collected)."""
        queries = list(
            self.db.scalars(
                select(PlanTaskRecord.title)
                .join(ResearchPlanRecord, ResearchPlanRecord.id == PlanTaskRecord.plan_id)
                .where(
                    ResearchPlanRecord.research_id == research_id,
                    PlanTaskRecord.task_type == TaskType.SEARCH,
                )
            )
        )
        titles = [
            d.title
            for d in self.document_service.get_documents_by_research(
                research_id, limit=200
            )
        ]
        return queries, titles

    def load_prior_claims(
        self, research_id: uuid.UUID, exclude_ids: list[uuid.UUID]
    ) -> list[tuple[Claim, ConfidenceLevel]]:
        """Claims from earlier rounds validated SUPPORTED, with their confidence."""
        excluded = set(exclude_ids)
        supported = set(
            self.db.scalars(
                select(ValidationRecord.claim_id).where(
                    ValidationRecord.research_id == research_id,
                    ValidationRecord.status == ValidationStatus.SUPPORTED,
                )
            )
        )
        levels = {
            row.claim_id: row.level
            for row in self.db.scalars(
                select(ConfidenceRecord).where(ConfidenceRecord.research_id == research_id)
            )
        }
        out = []
        for record in self.db.scalars(
            select(ClaimRecord)
            .where(ClaimRecord.research_id == research_id)
            .order_by(ClaimRecord.id.asc())
        ):
            if record.claim_id in excluded or record.claim_id not in supported:
                continue
            level = levels.get(record.claim_id)
            if level is None:
                continue
            out.append(
                (
                    Claim(
                        claim_id=record.claim_id,
                        text=record.text,
                        chunk_ids=[uuid.UUID(str(c)) for c in record.chunk_ids or []],
                        document_id=record.document_id,
                        page_number=record.page_number,
                        extracted_at=record.extracted_at,
                    ),
                    level,
                )
            )
        return out

    def save_plan(self, plan) -> None:
        """Persist the generated plan (research_plans / plan_tasks)."""
        self._plan_service.save_plan(plan)

    def persist_evidence_chain(self, state: ResearchWorkflowState) -> None:
        """Persist the epistemological chain carried by ``state`` (RDA-061)."""
        self._evidence_chain_repo.persist(state)

    # --- helpers -------------------------------------------------------------

    def _persist_results(self, results: list) -> list:
        """Persist unseen results and return only those (already-known ones dropped)."""
        existing = self.document_service.get_documents_by_research(
            self.research_id, limit=1000
        )
        existing_keys = {
            (doc.doi or "").lower() for doc in existing
        } | {
            (doc.title or "").strip().lower() for doc in existing
        }
        new_results = [
            r
            for r in results
            if (r.doi or "").lower() not in existing_keys
            and (r.title or "").strip().lower() not in existing_keys
        ]
        if not new_results:
            return []
        documents = self.document_service.save_search_results(
            self.research_id, new_results
        )
        for document in documents:
            self._doc_by_selection_id[_selection_id_from_document(document)] = document
        return new_results

    def _find_document(self, doc_id: uuid.UUID) -> Document | None:
        for document in self.document_service.get_documents_by_research(
            self.research_id, limit=1000
        ):
            if _selection_id_from_document(document) == doc_id:
                self._doc_by_selection_id[doc_id] = document
                return document
        return None


def build_workflow_services(
    db: Session, research_id: uuid.UUID, **service_overrides
) -> WorkflowServices:
    """Build the real WorkflowServices for one research.

    Shared by ``build_research_nodes`` (the full graph) and callers that only
    need one operation off it directly, e.g. ``process_pending_documents``
    (RDA-067), without paying for or risking the rest of the graph.
    """
    return WorkflowServices(db, research_id, **service_overrides)


def build_research_nodes(
    db: Session, research_id: uuid.UUID, **service_overrides
) -> ResearchNodes:
    """Build a ResearchNodes wired to the real services for one research.

    ``service_overrides`` are forwarded to WorkflowServices so tests can
    substitute fakes (e.g. ``search_service=...``, ``llm=...``).
    """
    services = build_workflow_services(db, research_id, **service_overrides)
    return ResearchNodes(
        planner=services.planner,
        # The search node calls ``self._search.search(query)``, so it needs
        # the services object (which exposes ``.search``), not the bound method.
        search=services,
        retriever=services.retriever,
        claim_extractor=services.claim_extractor,
        evidence_extractor=services.evidence_extractor,
        processor=services.process,
        llm=services.llm,
        research_loader=services.research_loader,
        summary_saver=services.save_summary,
        # Used by the selection node to score search results against the
        # research question (RDA-058).
        embedding_provider=services.embedding_service.provider,
        # Epistemological chain (RDA-061): wire the orphan services and the
        # adapters that resolve document sources and persist the chain.
        validator=services.validator,
        provenance_resolver=services.provenance_resolver,
        confidence_scorer=services.confidence_scorer,
        document_resolver=services.resolve_document_source,
        evidence_persister=services.persist_evidence_chain,
        plan_saver=services.save_plan,
        history_loader=services.load_history,
        prior_claims_loader=services.load_prior_claims,
    )
