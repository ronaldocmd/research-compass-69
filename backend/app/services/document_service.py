"""Business rules for Document (RDA-017).

Persists NormalizedSearchResult entries (RDA-011/RDA-015, produced by
SearchService with deduplication from RDA-016) against a Research. Raises
DocumentNotFoundError / ResearchNotFoundError; the API layer maps them to
HTTP 404 so the service stays framework-agnostic, following the same
convention as ResearchService (RDA-006).
"""

import uuid

from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.repositories.research_repository import ResearchRepository
from app.schemas.document import KNOWN_SOURCES, DocumentCreate
from app.schemas.search import NormalizedSearchResult


class DocumentNotFoundError(Exception):
    """Raised when a Document id does not exist."""

    def __init__(self, document_id: uuid.UUID) -> None:
        super().__init__(f"Document {document_id} not found")
        self.document_id = document_id


class ResearchNotFoundError(Exception):
    """Raised when a Research id does not exist."""

    def __init__(self, research_id: uuid.UUID) -> None:
        super().__init__(f"Research {research_id} not found")
        self.research_id = research_id


class DocumentService:
    def __init__(self, db: Session) -> None:
        self.repository = DocumentRepository(db)
        self._research_repository = ResearchRepository(db)

    def save_search_results(
        self, research_id: uuid.UUID, results: list[NormalizedSearchResult]
    ) -> list[Document]:
        """Persist search results as Documents linked to a Research.

        Args:
            research_id: The Research that ran the search.
            results: Normalized results (already deduplicated, if desired).

        Returns:
            The created Document rows, status="pending".

        Raises:
            ResearchNotFoundError: If research_id does not exist.
        """
        self._require_research(research_id)

        if not results:
            return []

        documents_data = [
            self._to_document_values(
                DocumentCreate(
                    research_id=research_id,
                    source=result.source,
                    external_id=result.external_id,
                    title=result.title or "(sem título)",
                    authors=result.authors,
                    publication_year=result.publication_year,
                    doi=result.doi,
                    url=result.url,
                    abstract=result.abstract,
                    metadata=result.metadata,
                    status=DocumentStatus.PENDING,
                )
            )
            for result in results
        ]
        return self.repository.bulk_create(documents_data)

    @staticmethod
    def _to_document_values(payload: DocumentCreate) -> dict:
        """DocumentCreate.model_dump() but with "metadata" renamed to the
        ORM attribute "document_metadata" (see app.models.document.Document
        and app.schemas.document for why the names differ)."""
        values = payload.model_dump()
        values["document_metadata"] = values.pop("metadata")
        return values

    def get_documents_by_research(
        self, research_id: uuid.UUID, *, skip: int = 0, limit: int = 50
    ) -> list[Document]:
        self._require_research(research_id)
        return self.repository.get_by_research_id(research_id, skip=skip, limit=limit)

    def get_document(self, document_id: uuid.UUID) -> Document:
        document = self.repository.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document

    def update_document_status(self, document_id: uuid.UUID, status: DocumentStatus) -> Document:
        document = self.get_document(document_id)
        return self.repository.update(document, status=status)

    def _require_research(self, research_id: uuid.UUID) -> None:
        if self._research_repository.get(research_id) is None:
            raise ResearchNotFoundError(research_id)


def is_known_source(source: str) -> bool:
    """Whether ``source`` is a search provider the system recognizes (RDA-017)."""
    return source in KNOWN_SOURCES
