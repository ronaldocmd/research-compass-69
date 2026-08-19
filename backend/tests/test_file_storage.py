"""Tests for FileStorage (RDA-019).

Uses a temporary directory so no test touches the real storage location.
"""

import uuid

import pytest

from app.services.storage.exceptions import (
    FileNotFoundError,
    FileTooLargeError,
    InvalidFileTypeError,
)
from app.services.storage.storage import FileStorage

PDF_BYTES = b"%PDF-1.4 fake pdf content"


@pytest.fixture
def storage(tmp_path) -> FileStorage:
    return FileStorage(base_dir=tmp_path)


def test_save_writes_file_and_returns_path(storage: FileStorage) -> None:
    document_id = uuid.uuid4()

    path = storage.save(document_id, PDF_BYTES, {"content_type": "application/pdf"})

    assert str(document_id) in path
    with open(path, "rb") as fh:
        assert fh.read() == PDF_BYTES


def test_save_returns_absolute_path_under_document_dir(storage: FileStorage) -> None:
    document_id = uuid.uuid4()

    path = storage.save(document_id, PDF_BYTES, {"content_type": "application/pdf"})

    assert str(document_id) in path
    assert path.endswith("document.bin")


def test_get_returns_stored_bytes(storage: FileStorage) -> None:
    document_id = uuid.uuid4()
    storage.save(document_id, PDF_BYTES, {"content_type": "application/pdf"})

    assert storage.get(document_id) == PDF_BYTES


def test_get_raises_when_file_missing(storage: FileStorage) -> None:
    with pytest.raises(FileNotFoundError):
        storage.get(uuid.uuid4())


def test_delete_removes_file_and_returns_true(storage: FileStorage) -> None:
    document_id = uuid.uuid4()
    storage.save(document_id, PDF_BYTES, {"content_type": "application/pdf"})

    assert storage.delete(document_id) is True
    with pytest.raises(FileNotFoundError):
        storage.get(document_id)


def test_delete_returns_false_when_no_file(storage: FileStorage) -> None:
    assert storage.delete(uuid.uuid4()) is False


def test_save_rejects_invalid_content_type(storage: FileStorage) -> None:
    with pytest.raises(InvalidFileTypeError):
        storage.save(uuid.uuid4(), b"<html></html>", {"content_type": "text/html"})


def test_save_rejects_file_too_large(storage: FileStorage) -> None:
    small_storage = FileStorage(base_dir=storage._base_dir, validator=__import__(
        "app.services.storage.validator", fromlist=["FileValidator"]
    ).FileValidator(max_size=1024))

    with pytest.raises(FileTooLargeError):
        small_storage.save(uuid.uuid4(), b"a" * 5000, {"content_type": "application/pdf"})


def test_save_requires_content_type_in_metadata(storage: FileStorage) -> None:
    with pytest.raises(InvalidFileTypeError):
        storage.save(uuid.uuid4(), PDF_BYTES, {})
