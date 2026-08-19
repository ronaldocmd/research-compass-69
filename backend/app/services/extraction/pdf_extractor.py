"""PDFExtractor (RDA-020, structure detection added in RDA-021).

Transforms a digital PDF (with embedded text) into structured text,
preserving page numbers so any excerpt can be traced back to its page in
the original document. Uses ``pypdf`` (the maintained successor to
PyPDF2) for parsing.

RDA-021 adds a second, non-breaking method (``extract_structured``) that
reuses the same ``pypdf`` parser to additionally detect headings,
paragraphs and basic tables via font-size and layout heuristics, since
pypdf has no built-in structure model. ``extract`` (RDA-020) is untouched
and keeps returning plain, page-aware text.

OCR and chunking remain out of scope (see RDA-020/RDA-022).
"""

import re
import statistics
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.extraction.exceptions import CorruptedPDFError, PDFNotFoundError
from app.services.extraction.schemas import (
    DocumentElement,
    ExtractedPage,
    ExtractionResult,
    StructuredExtractionResult,
    StructuredPage,
)

_TABLE_COLUMN_GAP = re.compile(r" {3,}")
_HEADING_FONT_RATIO = 1.15
_HEADING_MAX_CHARS = 120


class PDFExtractor:
    """Extracts structured, page-aware text from digital PDFs."""

    def extract(self, file_path: str, *, document_id: uuid.UUID | None = None) -> ExtractionResult:
        """Extract text from ``file_path``, page by page.

        Args:
            file_path: Path to the PDF file on disk.
            document_id: Optional Document this extraction belongs to.

        Returns:
            An ExtractionResult with one ExtractedPage per page.

        Raises:
            PDFNotFoundError: If ``file_path`` does not exist.
            CorruptedPDFError: If the file is not a readable PDF.
        """
        path = Path(file_path)
        if not path.is_file():
            raise PDFNotFoundError(file_path)

        try:
            reader = PdfReader(str(path))
            pages: list[ExtractedPage] = []
            for index, pdf_page in enumerate(reader.pages, start=1):
                text = pdf_page.extract_text() or ""
                pages.append(
                    ExtractedPage(
                        page_number=index,
                        text=text,
                        char_count=len(text),
                    )
                )
        except PdfReadError as exc:
            raise CorruptedPDFError(file_path, reason=str(exc)) from exc
        except Exception as exc:
            raise CorruptedPDFError(file_path, reason=str(exc)) from exc

        return ExtractionResult(
            document_id=document_id,
            pages=pages,
            total_pages=len(pages),
            total_chars=sum(page.char_count for page in pages),
            extracted_at=datetime.now(UTC),
        )

    def extract_structured(
        self, file_path: str, *, document_id: uuid.UUID | None = None
    ) -> StructuredExtractionResult:
        """Extract text from ``file_path``, preserving basic structure.

        Reuses the same ``pypdf`` parser as :meth:`extract`, but additionally
        groups text into headings, paragraphs and basic tables using
        font-size and layout heuristics (pypdf has no structure model of
        its own). If a PDF is too simple to yield any signal, every line
        is returned as a paragraph, which is an acceptable outcome.

        Raises:
            PDFNotFoundError: If ``file_path`` does not exist.
            CorruptedPDFError: If the file is not a readable PDF.
        """
        path = Path(file_path)
        if not path.is_file():
            raise PDFNotFoundError(file_path)

        try:
            reader = PdfReader(str(path))
            pages: list[StructuredPage] = []
            position = 0
            for index, pdf_page in enumerate(reader.pages, start=1):
                lines = self._extract_lines(pdf_page)
                elements, position = self._detect_elements(lines, index, position)
                pages.append(StructuredPage(page_number=index, elements=elements))
        except PdfReadError as exc:
            raise CorruptedPDFError(file_path, reason=str(exc)) from exc
        except Exception as exc:
            raise CorruptedPDFError(file_path, reason=str(exc)) from exc

        return StructuredExtractionResult(
            document_id=document_id,
            pages=pages,
            total_pages=len(pages),
            extracted_at=datetime.now(UTC),
        )

    def _extract_lines(self, pdf_page) -> list[tuple[str, float]]:
        """Return ``(text, font_size)`` per line, in rendering order.

        Text fragments sharing the same vertical position (``tm`` row) are
        joined into a single line; the largest font size seen on the line
        wins, since a heading is only as small as its smallest glyph.
        """
        chunks: list[tuple[str, float, float]] = []

        def visitor(text: str, cm, tm, font_dict, font_size) -> None:  # noqa: ANN001
            if text and text.strip():
                y = round(float(tm[5]), 1) if tm is not None else 0.0
                size = float(font_size) if font_size else 0.0
                chunks.append((text, y, size))

        pdf_page.extract_text(visitor_text=visitor)

        lines: list[tuple[str, float]] = []
        current_y: float | None = None
        current_text = ""
        current_size = 0.0
        for text, y, size in chunks:
            if current_y is None or abs(y - current_y) > 1:
                if current_text.strip():
                    lines.append((current_text.strip(), current_size))
                current_text, current_y, current_size = text, y, size
            else:
                current_text += text
                current_size = max(current_size, size)
        if current_text.strip():
            lines.append((current_text.strip(), current_size))
        return lines

    def _detect_elements(
        self, lines: list[tuple[str, float]], page_number: int, position: int
    ) -> tuple[list[DocumentElement], int]:
        """Group ``lines`` into heading/paragraph/table elements.

        Heuristics (pypdf exposes no structure model):
        - Heading: font size notably larger than the page's body font size
          and a short line (few characters).
        - Table: two or more consecutive lines with 2+ column-like gaps
          (3+ spaces between tokens).
        - Paragraph: everything else, merging consecutive plain lines.
        """
        if not lines:
            return [], position

        sizes = [size for _, size in lines if size > 0]
        body_size = statistics.median(sizes) if sizes else 0.0
        heading_sizes = sorted(
            {size for size in sizes if body_size and size >= body_size * _HEADING_FONT_RATIO},
            reverse=True,
        )

        elements: list[DocumentElement] = []
        paragraph_buffer: list[str] = []
        table_buffer: list[str] = []

        def flush_paragraph() -> None:
            nonlocal position
            if paragraph_buffer:
                elements.append(
                    DocumentElement(
                        type="paragraph",
                        level=None,
                        text=" ".join(paragraph_buffer),
                        page_number=page_number,
                        position=position,
                    )
                )
                position += 1
                paragraph_buffer.clear()

        def flush_table() -> None:
            nonlocal position
            if table_buffer:
                elements.append(
                    DocumentElement(
                        type="table",
                        level=None,
                        text="\n".join(table_buffer),
                        page_number=page_number,
                        position=position,
                    )
                )
                position += 1
                table_buffer.clear()

        for text, size in lines:
            is_heading = bool(heading_sizes) and size in heading_sizes and len(text) <= _HEADING_MAX_CHARS
            is_table_row = len(_TABLE_COLUMN_GAP.split(text)) >= 3

            if is_table_row and not is_heading:
                flush_paragraph()
                table_buffer.append(text)
                continue
            flush_table()

            if is_heading:
                flush_paragraph()
                elements.append(
                    DocumentElement(
                        type="heading",
                        level=heading_sizes.index(size) + 1,
                        text=text,
                        page_number=page_number,
                        position=position,
                    )
                )
                position += 1
            else:
                paragraph_buffer.append(text)

        flush_table()
        flush_paragraph()
        return elements, position
