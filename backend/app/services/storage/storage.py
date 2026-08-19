"""FileStorage (RDA-019).

Persists downloaded file bytes on the local filesystem under
``{base_dir}/{document_id}/`` and returns the storage path. Only file
metadata (hash, path, size) is meant to be stored in the database — never
the file bytes themselves.
"""

import uuid
from pathlib import Path

from app.core.config import settings
from app.services.storage.exceptions import FileNotFoundError, StorageError
from app.services.storage.validator import FileValidator

FILENAME = "document.bin"


class FileStorage:
    """Stores and retrieves document files on the local filesystem."""

    def __init__(
        self,
        *,
        base_dir: str | Path | None = None,
        validator: FileValidator | None = None,
    ) -> None:
        self._base_dir = Path(base_dir if base_dir is not None else settings.STORAGE_BASE_DIR)
        self._validator = validator or FileValidator()

    def save(self, document_id: uuid.UUID, content: bytes, metadata: dict) -> str:
        """Validate and store ``content`` for ``document_id``.

        Args:
            document_id: The Document this file belongs to.
            content: The raw file bytes.
            metadata: Download metadata; must include ``content_type``.

        Returns:
            The absolute storage path of the saved file.

        Raises:
            FileValidationError: If the file fails validation.
            StorageError: If the file cannot be written.
        """
        content_type = metadata.get("content_type", "")
        self._validator.validate(content, content_type)

        directory = self._base_dir / str(document_id)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / FILENAME
            path.write_bytes(content)
        except OSError as exc:
            raise StorageError(f"Failed to write file for {document_id}: {exc}") from exc
        return str(path)

    def get(self, document_id: uuid.UUID) -> bytes:
        """Return the stored bytes for ``document_id``.

        Raises:
            FileNotFoundError: If no stored file exists for the document.
        """
        path = self._path_for(document_id)
        if not path.is_file():
            raise FileNotFoundError(document_id)
        try:
            return path.read_bytes()
        except OSError as exc:
            raise StorageError(f"Failed to read file for {document_id}: {exc}") from exc

    def delete(self, document_id: uuid.UUID) -> bool:
        """Delete the stored file (and its directory) for ``document_id``.

        Returns True if a file was removed, False if none existed.
        """
        path = self._path_for(document_id)
        if not path.is_file():
            return False
        try:
            path.unlink()
            directory = path.parent
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        except OSError as exc:
            raise StorageError(f"Failed to delete file for {document_id}: {exc}") from exc
        return True

    def _path_for(self, document_id: uuid.UUID) -> Path:
        return self._base_dir / str(document_id) / FILENAME
