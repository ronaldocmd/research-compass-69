"""Tests for PDFExtractor.extract_structured (RDA-021).

Uses fixture PDFs under tests/fixtures/pdfs/: a PDF with headings, a PDF
with a table, and a simple PDF with no structural signal.
"""

from pathlib import Path

import pytest

from app.services.extraction.exceptions import CorruptedPDFError, PDFNotFoundError
from app.services.extraction.pdf_extractor import PDFExtractor
from app.services.extraction.schemas import StructuredExtractionResult

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "pdfs"


@pytest.fixture
def extractor() -> PDFExtractor:
    return PDFExtractor()


def test_extract_structured_detects_headings(extractor: PDFExtractor) -> None:
    result = extractor.extract_structured(str(FIXTURES_DIR / "headings.pdf"))

    assert isinstance(result, StructuredExtractionResult)
    elements = result.pages[0].elements
    headings = [el for el in elements if el.type == "heading"]

    assert [h.text for h in headings] == ["Research Report", "Introduction", "Methodology"]
    assert headings[0].level == 1
    assert headings[1].level == 2 and headings[2].level == 2


def test_extract_structured_groups_paragraphs(extractor: PDFExtractor) -> None:
    result = extractor.extract_structured(str(FIXTURES_DIR / "headings.pdf"))

    paragraphs = [el for el in result.pages[0].elements if el.type == "paragraph"]

    assert len(paragraphs) == 2
    assert "introduction paragraph" in paragraphs[0].text


def test_extract_structured_detects_table(extractor: PDFExtractor) -> None:
    result = extractor.extract_structured(str(FIXTURES_DIR / "table.pdf"))

    elements = result.pages[0].elements
    tables = [el for el in elements if el.type == "table"]

    assert len(tables) == 1
    assert "Alpha" in tables[0].text
    assert "Beta" in tables[0].text
    assert tables[0].text.count("\n") >= 2


def test_extract_structured_simple_pdf_returns_paragraphs_only(extractor: PDFExtractor) -> None:
    result = extractor.extract_structured(str(FIXTURES_DIR / "single_page.pdf"))

    elements = result.pages[0].elements
    assert all(el.type == "paragraph" for el in elements)
    assert any("Hello world" in el.text for el in elements)


def test_extract_structured_positions_are_sequential_across_pages(extractor: PDFExtractor) -> None:
    result = extractor.extract_structured(str(FIXTURES_DIR / "multi_page.pdf"))

    all_positions = [el.position for page in result.pages for el in page.elements]

    assert all_positions == sorted(all_positions)
    assert len(set(all_positions)) == len(all_positions)


def test_extract_structured_empty_pdf_returns_no_elements(extractor: PDFExtractor) -> None:
    result = extractor.extract_structured(str(FIXTURES_DIR / "empty.pdf"))

    assert result.total_pages == 1
    assert result.pages[0].elements == []


def test_extract_structured_corrupted_pdf_raises(extractor: PDFExtractor) -> None:
    with pytest.raises(CorruptedPDFError):
        extractor.extract_structured(str(FIXTURES_DIR / "corrupted.pdf"))


def test_extract_structured_missing_file_raises(extractor: PDFExtractor) -> None:
    with pytest.raises(PDFNotFoundError):
        extractor.extract_structured(str(FIXTURES_DIR / "does_not_exist.pdf"))


def test_basic_extract_still_works_unchanged(extractor: PDFExtractor) -> None:
    """RDA-020's plain extract() must remain fully functional (RDA-021 compat)."""
    result = extractor.extract(str(FIXTURES_DIR / "headings.pdf"))

    assert result.total_pages == 1
    assert "Research Report" in result.pages[0].text
