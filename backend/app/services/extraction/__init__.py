"""PDF extraction service (RDA-020)."""

from app.services.extraction.exceptions import (
    CorruptedPDFError,
    ExtractionError,
    PDFNotFoundError,
)
from app.services.extraction.pdf_extractor import PDFExtractor
from app.services.extraction.schemas import (
    DocumentElement,
    ExtractedPage,
    ExtractionResult,
    StructuredExtractionResult,
    StructuredPage,
)

__all__ = [
    "CorruptedPDFError",
    "DocumentElement",
    "ExtractedPage",
    "ExtractionError",
    "ExtractionResult",
    "PDFExtractor",
    "PDFNotFoundError",
    "StructuredExtractionResult",
    "StructuredPage",
]
