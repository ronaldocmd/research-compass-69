"""Tests for PDFExtractor (RDA-020).

Uses fixture PDFs under tests/fixtures/pdfs/: a single-page PDF, a
multi-page PDF, an empty (no-text) PDF, and a corrupted PDF.
"""

import uuid
from pathlib import Path

import pytest

from app.services.extraction.exceptions import CorruptedPDFError, PDFNotFoundError
from app.services.extraction.pdf_extractor import PDFExtractor
from app.services.extraction.schemas import ExtractionResult

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "pdfs"


@pytest.fixture
def extractor() -> PDFExtractor:
    return PDFExtractor()


def test_extract_single_page_pdf(extractor: PDFExtractor) -> None:
    result = extractor.extract(str(FIXTURES_DIR / "single_page.pdf"))

    assert isinstance(result, ExtractionResult)
    assert result.total_pages == 1
    assert len(result.pages) == 1
    assert result.pages[0].page_number == 1
    assert "Hello world" in result.pages[0].text
    assert result.pages[0].char_count == len(result.pages[0].text)
    assert result.total_chars == result.pages[0].char_count


def test_extract_multi_page_pdf(extractor: PDFExtractor) -> None:
    result = extractor.extract(str(FIXTURES_DIR / "multi_page.pdf"))

    assert result.total_pages == 3
    assert [page.page_number for page in result.pages] == [1, 2, 3]
    assert "Page one" in result.pages[0].text
    assert "Page two" in result.pages[1].text
    assert "Page three" in result.pages[2].text
    assert result.total_chars == sum(page.char_count for page in result.pages)


def test_extract_preserves_page_locatability(extractor: PDFExtractor) -> None:
    result = extractor.extract(str(FIXTURES_DIR / "multi_page.pdf"))

    excerpt = "Methodology and related work"
    matching_pages = [page.page_number for page in result.pages if excerpt in page.text]

    assert matching_pages == [2]


def test_extract_empty_pdf(extractor: PDFExtractor) -> None:
    result = extractor.extract(str(FIXTURES_DIR / "empty.pdf"))

    assert result.total_pages == 1
    assert result.pages[0].text == ""
    assert result.pages[0].char_count == 0
    assert result.total_chars == 0


def test_extract_corrupted_pdf_raises(extractor: PDFExtractor) -> None:
    with pytest.raises(CorruptedPDFError):
        extractor.extract(str(FIXTURES_DIR / "corrupted.pdf"))


def test_extract_missing_file_raises(extractor: PDFExtractor) -> None:
    with pytest.raises(PDFNotFoundError):
        extractor.extract(str(FIXTURES_DIR / "does_not_exist.pdf"))


def test_extract_attaches_document_id_when_provided(extractor: PDFExtractor) -> None:
    document_id = uuid.uuid4()

    result = extractor.extract(str(FIXTURES_DIR / "single_page.pdf"), document_id=document_id)

    assert result.document_id == document_id


def test_extract_document_id_defaults_to_none(extractor: PDFExtractor) -> None:
    result = extractor.extract(str(FIXTURES_DIR / "single_page.pdf"))

    assert result.document_id is None
