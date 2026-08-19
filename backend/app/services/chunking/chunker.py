"""DocumentChunker (RDA-022).

Splits a StructuredExtractionResult (RDA-021) into retrieval-sized Chunks,
deterministically: the same extraction result and configuration always
produce the same chunks, in the same order, with the same ``chunk_id``s.
"""

import uuid
from datetime import UTC, datetime

from app.core.config import settings
from app.services.chunking.schemas import Chunk, ChunkingResult
from app.services.chunking.strategies import (
    ChunkingStrategy,
    StructureAwareChunkingStrategy,
)
from app.services.extraction.schemas import StructuredExtractionResult

# Fixed namespace so chunk_id is a deterministic function of (document_id,
# index, text) rather than a random uuid4.
_CHUNK_ID_NAMESPACE = uuid.UUID("6f2f6e0a-9d3f-4b8a-9c0a-9a2e5b7d5a1e")


class DocumentChunker:
    """Splits structured extraction results into deterministic chunks."""

    def __init__(
        self,
        *,
        chunk_size: int | None = None,
        strategy: ChunkingStrategy | None = None,
    ) -> None:
        self._chunk_size = chunk_size if chunk_size is not None else settings.CHUNK_SIZE_CHARS
        self._strategy = strategy or StructureAwareChunkingStrategy()

    def chunk(self, extraction_result: StructuredExtractionResult) -> ChunkingResult:
        """Split ``extraction_result`` into Chunks using the configured strategy."""
        groups = self._strategy.split(extraction_result, self._chunk_size)

        chunks = [
            Chunk(
                chunk_id=self._deterministic_chunk_id(extraction_result.document_id, index, group.text),
                document_id=extraction_result.document_id,
                text=group.text,
                page_number=group.page_number,
                section=group.section,
                index=index,
                char_count=len(group.text),
            )
            for index, group in enumerate(groups)
        ]

        return ChunkingResult(
            document_id=extraction_result.document_id,
            chunks=chunks,
            total_chunks=len(chunks),
            strategy=self._strategy.name,
            chunked_at=datetime.now(UTC),
        )

    @staticmethod
    def _deterministic_chunk_id(document_id: uuid.UUID | None, index: int, text: str) -> uuid.UUID:
        seed = f"{document_id}:{index}:{text}"
        return uuid.uuid5(_CHUNK_ID_NAMESPACE, seed)
