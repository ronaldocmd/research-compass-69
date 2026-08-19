"""FileValidator (RDA-019).

Validates a downloaded file's content type, size and integrity (SHA-256)
before it is stored. Only PDF is accepted for now; parsing is a later
ticket (RDA-020).
"""

import hashlib

from app.core.config import settings
from app.services.storage.exceptions import (
    FileIntegrityError,
    FileTooLargeError,
    InvalidFileTypeError,
)

ALLOWED_CONTENT_TYPES = {"application/pdf"}


class FileValidator:
    """Validates content type, size and computes the SHA-256 hash."""

    def __init__(
        self,
        *,
        max_size: int | None = None,
        allowed_content_types: set[str] | None = None,
    ) -> None:
        self._max_size = max_size if max_size is not None else settings.DOWNLOAD_MAX_SIZE_BYTES
        self._allowed_content_types = (
            allowed_content_types
            if allowed_content_types is not None
            else set(ALLOWED_CONTENT_TYPES)
        )

    def validate(self, content: bytes, content_type: str) -> str:
        """Validate ``content`` and return its SHA-256 hex digest.

        Args:
            content: The raw file bytes.
            content_type: The file's MIME type (from the download).

        Returns:
            The SHA-256 hex digest of ``content``.

        Raises:
            InvalidFileTypeError: If content_type is not allowed.
            FileTooLargeError: If content exceeds the max size.
        """
        self._validate_content_type(content_type)
        self._validate_size(content)
        return self.sha256(content)

    def _validate_content_type(self, content_type: str) -> None:
        normalized = content_type.strip().lower()
        if normalized not in self._allowed_content_types:
            raise InvalidFileTypeError(
                f"Content-Type {content_type!r} is not allowed; expected one of "
                f"{sorted(self._allowed_content_types)}"
            )

    def _validate_size(self, content: bytes) -> None:
        if len(content) > self._max_size:
            raise FileTooLargeError(
                f"File size {len(content)} exceeds max size {self._max_size}"
            )

    @staticmethod
    def sha256(content: bytes) -> str:
        """Return the SHA-256 hex digest of ``content``."""
        return hashlib.sha256(content).hexdigest()

    def verify_hash(self, content: bytes, expected_hash: str) -> None:
        """Raise FileIntegrityError if ``content``'s hash differs from ``expected_hash``."""
        actual = self.sha256(content)
        if actual != expected_hash:
            raise FileIntegrityError(
                f"Hash mismatch: expected {expected_hash}, got {actual}"
            )
