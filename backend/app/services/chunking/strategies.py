"""Chunking strategies (RDA-022).

A strategy turns a ``StructuredExtractionResult`` (RDA-021) into an
ordered list of ``ChunkGroup``s. It never assigns ``chunk_id``/``index``
(the ``DocumentChunker`` does that), and it never touches the clock or
randomness, so the same input always yields the same groups.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.services.extraction.schemas import StructuredExtractionResult


@dataclass(frozen=True)
class ChunkGroup:
    """One accumulated slice of text, before it becomes a ``Chunk``."""

    text: str
    page_number: int
    section: str | None


class ChunkingStrategy(Protocol):
    """A deterministic text -> chunk-groups splitting strategy."""

    name: str

    def split(self, extraction_result: StructuredExtractionResult, chunk_size: int) -> list[ChunkGroup]:
        ...


class StructureAwareChunkingStrategy:
    """Accumulates structural elements up to ``chunk_size`` characters.

    Rules (per RDA-022):
    - Never splits a single element (heading/paragraph/table) in half.
    - A heading starts a new chunk when possible, so section boundaries
      are respected rather than crossed mid-chunk.
    - A chunk's ``page_number`` is the page of its last included element.
    - A chunk's ``section`` is the most recent heading seen so far, so
      every chunk can be traced back to the section it belongs to.
    """

    name = "structure_aware"

    def split(self, extraction_result: StructuredExtractionResult, chunk_size: int) -> list[ChunkGroup]:
        groups: list[ChunkGroup] = []
        texts: list[str] = []
        page_number: int | None = None
        section: str | None = None
        running_section: str | None = None

        def current_length() -> int:
            return len("\n\n".join(texts))

        def flush() -> None:
            if texts:
                groups.append(
                    ChunkGroup(text="\n\n".join(texts), page_number=page_number, section=section)
                )

        for page in extraction_result.pages:
            for element in page.elements:
                text = element.text.strip()
                if not text:
                    continue

                if element.type == "heading":
                    running_section = text
                    if texts:
                        flush()
                        texts = []
                    section = running_section

                projected_length = current_length() + len(text) + (2 if texts else 0)
                if texts and projected_length > chunk_size:
                    flush()
                    texts = []
                    section = running_section

                texts.append(text)
                page_number = element.page_number

        flush()
        return groups
