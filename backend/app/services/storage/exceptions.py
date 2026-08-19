"""Domain exceptions for file validation and storage (RDA-019).

Follows the same convention as app.services.search.exceptions and
app.services.downloader.exceptions: a base class plus specific subclasses.
"""


class StorageError(Exception):
    """Base class for every error raised by the storage layer."""


class FileValidationError(StorageError):
    """A file failed validation (type, size, integrity)."""


class InvalidFileTypeError(FileValidationError):
    """The file's content type is not allowed."""


class FileTooLargeError(FileValidationError):
    """The file exceeds the configured maximum size."""


class FileIntegrityError(FileValidationError):
    """The file failed an integrity check (e.g. hash mismatch)."""


class FileNotFoundError(StorageError):
    """A stored file could not be found."""

    def __init__(self, document_id: object) -> None:
        super().__init__(f"Stored file for document {document_id} not found")
        self.document_id = document_id
