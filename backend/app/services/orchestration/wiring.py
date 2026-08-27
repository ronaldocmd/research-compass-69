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

from app.models.chunk import ChunkRecord
from app.models.document import Document, DocumentStatus
from app.repositories.evidence_chain_repository import EvidenceChainRepository
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
from app.services.research_service import ResearchService
from app.services.retrieval.retriever import DocumentRetriever
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

        # Shared, mutable retrieval index: the retriever reads it and the
        # processor appends to it as documents are embedded.
        self._index: list[IndexedChunk] = []
        self.retriever = retriever or DocumentRetriever(index=self._index)

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
        results = self.search_service.search(query)
        self._persist_results(results)
        return results

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
            chunk_ids.append(chunk.chunk_id)

        self.db.commit()
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

    def persist_evidence_chain(self, state: ResearchWorkflowState) -> None:
        """Persist the epistemological chain carried by ``state`` (RDA-061)."""
        self._evidence_chain_repo.persist(state)

    # --- helpers -------------------------------------------------------------

    def _persist_results(self, results: list) -> None:
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
            return
        documents = self.document_service.save_search_results(
            self.research_id, new_results
        )
        for document in documents:
            self._doc_by_selection_id[_selection_id_from_document(document)] = document

    def _find_document(self, doc_id: uuid.UUID) -> Document | None:
        for document in self.document_service.get_documents_by_research(
            self.research_id, limit=1000
        ):
            if _selection_id_from_document(document) == doc_id:
                self._doc_by_selection_id[doc_id] = document
                return document
        return None


def build_research_nodes(
    db: Session, research_id: uuid.UUID, **service_overrides
) -> ResearchNodes:
    """Build a ResearchNodes wired to the real services for one research.

    ``service_overrides`` are forwarded to WorkflowServices so tests can
    substitute fakes (e.g. ``search_service=...``, ``llm=...``).
    """
    services = WorkflowServices(db, research_id, **service_overrides)
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
    )
