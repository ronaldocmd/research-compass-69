"""Tests for DocumentChunker (RDA-022).

Reuses PDFExtractor.extract_structured (RDA-021) against the existing
fixture PDFs under tests/fixtures/pdfs/ to build StructuredExtractionResult
inputs, then exercises the chunking behaviour itself.
"""

import uuid

import pytest

from app.services.chunking.chunker import DocumentChunker
from app.services.chunking.schemas import ChunkingResult
from app.services.extraction.pdf_extractor import PDFExtractor
from app.services.extraction.schemas import (
    DocumentElement,
    StructuredExtractionResult,
    StructuredPage,
)
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "pdfs"


@pytest.fixture
def extractor() -> PDFExtractor:
    return PDFExtractor()


def _long_paragraph_result(document_id: uuid.UUID | None = None) -> StructuredExtractionResult:
    """Build a synthetic result with several long paragraphs across pages."""
    paragraphs = [f"Paragraph number {i}. " * 20 for i in range(6)]
    pages = [
        StructuredPage(
            page_number=page_no,
            elements=[
                DocumentElement(
                    type="paragraph",
                    level=None,
                    text=text,
                    page_number=page_no,
                    position=position,
                )
            ],
        )
        for position, (page_no, text) in enumerate(zip([1, 1, 1, 2, 2, 2], paragraphs))
    ]
    from datetime import UTC, datetime

    return StructuredExtractionResult(
        document_id=document_id,
        pages=pages,
        total_pages=2,
        extracted_at=datetime.now(UTC),
    )


def test_short_document_produces_single_chunk(extractor: PDFExtractor) -> None:
    result = extractor.extract_structured(str(FIXTURES_DIR / "single_page.pdf"))
    chunker = DocumentChunker()

    chunking_result = chunker.chunk(result)

    assert isinstance(chunking_result, ChunkingResult)
    assert chunking_result.total_chunks == 1
    assert chunking_result.chunks[0].index == 0
    assert chunking_result.strategy == "structure_aware"


def test_long_document_produces_multiple_chunks() -> None:
    result = _long_paragraph_result()
    chunker = DocumentChunker(chunk_size=200)

    chunking_result = chunker.chunk(result)

    assert chunking_result.total_chunks > 1
    assert [c.index for c in chunking_result.chunks] == list(range(chunking_result.total_chunks))
    for chunk in chunking_result.chunks:
        assert chunk.char_count <= 200 or chunk.char_count == len(chunk.text)


def test_chunking_is_deterministic() -> None:
    result = _long_paragraph_result(document_id=uuid.uuid4())
    chunker = DocumentChunker(chunk_size=150)

    first = chunker.chunk(result)
    second = chunker.chunk(result)

    assert [c.text for c in first.chunks] == [c.text for c in second.chunks]
    assert [c.chunk_id for c in first.chunks] == [c.chunk_id for c in second.chunks]
    assert [c.page_number for c in first.chunks] == [c.page_number for c in second.chunks]


def test_chunks_preserve_page_number_and_section(extractor: PDFExtractor) -> None:
    result = extractor.extract_structured(str(FIXTURES_DIR / "headings.pdf"))
    chunker = DocumentChunker(chunk_size=1000)

    chunking_result = chunker.chunk(result)

    assert all(chunk.page_number == 1 for chunk in chunking_result.chunks)
    sections = {chunk.section for chunk in chunking_result.chunks}
    assert "Introduction" in sections or "Methodology" in sections or "Research Report" in sections


def test_chunks_do_not_split_paragraphs_mid_way() -> None:
    result = _long_paragraph_result()
    chunker = DocumentChunker(chunk_size=100)

    chunking_result = chunker.chunk(result)

    original_paragraphs = {(f"Paragraph number {i}. " * 20).strip() for i in range(6)}
    for chunk in chunking_result.chunks:
        for fragment in chunk.text.split("\n\n"):
            assert fragment in original_paragraphs


def test_chunk_document_id_propagates_from_extraction_result(extractor: PDFExtractor) -> None:
    document_id = uuid.uuid4()
    result = extractor.extract_structured(str(FIXTURES_DIR / "single_page.pdf"), document_id=document_id)
    chunker = DocumentChunker()

    chunking_result = chunker.chunk(result)

    assert chunking_result.document_id == document_id
    assert all(chunk.document_id == document_id for chunk in chunking_result.chunks)


def test_custom_chunk_size_is_respected() -> None:
    result = _long_paragraph_result()
    small_chunker = DocumentChunker(chunk_size=50)
    large_chunker = DocumentChunker(chunk_size=5000)

    small_result = small_chunker.chunk(result)
    large_result = large_chunker.chunk(result)

    assert small_result.total_chunks > large_result.total_chunks
    assert large_result.total_chunks == 1
