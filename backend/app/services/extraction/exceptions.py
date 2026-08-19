"""Domain exceptions for PDF extraction (RDA-020).

Follows the same convention as app.services.downloader.exceptions and
app.services.storage.exceptions: a base class plus specific subclasses.
"""


class ExtractionError(Exception):
    """Base class for every error raised by the extraction layer."""


class PDFNotFoundError(ExtractionError):
    """The PDF file to extract could not be found on disk."""

    def __init__(self, file_path: str) -> None:
        super().__init__(f"PDF file not found: {file_path}")
        self.file_path = file_path


class CorruptedPDFError(ExtractionError):
    """The PDF file could not be parsed (corrupted or not a valid PDF)."""

    def __init__(self, file_path: str, reason: str | None = None) -> None:
        message = f"Corrupted or unreadable PDF: {file_path}"
        if reason:
            message += f" ({reason})"
        super().__init__(message)
        self.file_path = file_path
