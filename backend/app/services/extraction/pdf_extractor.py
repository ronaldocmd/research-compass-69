"""PDFExtractor (RDA-020).

Transforms a digital PDF (with embedded text) into structured text,
preserving page numbers so any excerpt can be traced back to its page in
the original document. Uses ``pypdf`` (the maintained successor to
PyPDF2) for parsing.

OCR and structural analysis (headings, sections) are explicitly out of
scope for this ticket.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.extraction.exceptions import CorruptedPDFError, PDFNotFoundError
from app.services.extraction.schemas import ExtractedPage, ExtractionResult


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
