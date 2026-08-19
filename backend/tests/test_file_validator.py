"""Tests for FileValidator (RDA-019)."""

import hashlib

import pytest

from app.services.storage.exceptions import (
    FileIntegrityError,
    FileTooLargeError,
    InvalidFileTypeError,
)
from app.services.storage.validator import FileValidator

PDF_BYTES = b"%PDF-1.4 fake pdf content"


def test_validates_valid_pdf_and_returns_hash() -> None:
    validator = FileValidator()

    digest = validator.validate(PDF_BYTES, "application/pdf")

    assert digest == hashlib.sha256(PDF_BYTES).hexdigest()


def test_rejects_invalid_content_type() -> None:
    validator = FileValidator()

    with pytest.raises(InvalidFileTypeError):
        validator.validate(b"<html></html>", "text/html")


def test_rejects_missing_content_type() -> None:
    validator = FileValidator()

    with pytest.raises(InvalidFileTypeError):
        validator.validate(PDF_BYTES, "")


def test_rejects_file_too_large() -> None:
    validator = FileValidator(max_size=1024)

    with pytest.raises(FileTooLargeError):
        validator.validate(b"a" * 5000, "application/pdf")


def test_accepts_file_at_exact_max_size() -> None:
    validator = FileValidator(max_size=1024)
    content = b"a" * 1024

    digest = validator.validate(content, "application/pdf")

    assert digest == hashlib.sha256(content).hexdigest()


def test_sha256_matches_expected() -> None:
    assert FileValidator.sha256(PDF_BYTES) == hashlib.sha256(PDF_BYTES).hexdigest()


def test_verify_hash_passes_on_match() -> None:
    validator = FileValidator()
    digest = validator.sha256(PDF_BYTES)

    validator.verify_hash(PDF_BYTES, digest)


def test_verify_hash_raises_on_mismatch() -> None:
    validator = FileValidator()

    with pytest.raises(FileIntegrityError):
        validator.verify_hash(PDF_BYTES, "0" * 64)


def test_content_type_is_case_insensitive() -> None:
    validator = FileValidator()

    digest = validator.validate(PDF_BYTES, "Application/PDF")

    assert digest == hashlib.sha256(PDF_BYTES).hexdigest()
