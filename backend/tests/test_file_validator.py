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


def test_accepts_pdf_with_octet_stream_content_type() -> None:
    """RDA-060: a real PDF served as application/octet-stream (or another
    generic type) must be accepted via magic-byte sniffing."""
    validator = FileValidator()

    digest = validator.validate(PDF_BYTES, "application/octet-stream")

    assert digest == hashlib.sha256(PDF_BYTES).hexdigest()


def test_accepts_pdf_with_unknown_content_type() -> None:
    validator = FileValidator()

    digest = validator.validate(PDF_BYTES, "binary/octet-stream")

    assert digest == hashlib.sha256(PDF_BYTES).hexdigest()


def test_rejects_html_even_with_pdf_magic_absent() -> None:
    """A non-PDF payload with a generic content type must still be rejected."""
    validator = FileValidator()

    with pytest.raises(InvalidFileTypeError):
        validator.validate(b"<html>not a pdf</html>", "application/octet-stream")


def test_rejects_missing_content_type_for_non_pdf() -> None:
    """A non-PDF payload with no content type must be rejected (RDA-060)."""
    validator = FileValidator()

    with pytest.raises(InvalidFileTypeError):
        validator.validate(b"<html>not a pdf</html>", "")


def test_accepts_pdf_with_missing_content_type() -> None:
    """A real PDF with no content type is accepted via magic-byte sniffing."""
    validator = FileValidator()

    digest = validator.validate(PDF_BYTES, "")

    assert digest == hashlib.sha256(PDF_BYTES).hexdigest()


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
