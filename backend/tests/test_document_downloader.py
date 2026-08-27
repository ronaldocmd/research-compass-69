"""Tests for DocumentDownloader (RDA-018).

All HTTP calls are mocked via httpx.MockTransport: no test depends on a
real network or a real document URL.
"""

import httpx
import pytest

from app.services.downloader.downloader import MAX_REDIRECTS, DocumentDownloader
from app.services.downloader.exceptions import (
    DownloadError,
    DownloadHTTPError,
    DownloadTimeoutError,
    FileTooLargeError,
    InvalidContentTypeError,
)
from app.services.downloader.schemas import DownloadResult
from app.services.downloader.ssrf import SSRFBlockedError, SSRFGuard

PDF_BYTES = b"%PDF-1.4 fake pdf content"


class _PermissiveGuard(SSRFGuard):
    """Allows every URL; used so tests never depend on real DNS."""

    def validate(self, url: str) -> None:
        return None


def make_downloader(handler, **kwargs) -> DocumentDownloader:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    kwargs.setdefault("ssrf_guard", _PermissiveGuard())
    return DocumentDownloader(client=client, **kwargs)


def test_download_success_returns_bytes_and_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://example.org/paper.pdf"
        return httpx.Response(
            200,
            content=PDF_BYTES,
            headers={"content-type": "application/pdf", "content-length": str(len(PDF_BYTES))},
        )

    downloader = make_downloader(handler)
    result = downloader.download("https://example.org/paper.pdf")

    assert isinstance(result, DownloadResult)
    assert result.content == PDF_BYTES
    assert result.content_type == "application/pdf"
    assert result.size == len(PDF_BYTES)
    assert result.source_url == "https://example.org/paper.pdf"
    assert result.downloaded_at is not None


def test_download_raises_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    downloader = make_downloader(handler)
    with pytest.raises(DownloadTimeoutError):
        downloader.download("https://example.org/paper.pdf")


def test_download_raises_on_http_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"not found")

    downloader = make_downloader(handler)
    with pytest.raises(DownloadHTTPError) as exc_info:
        downloader.download("https://example.org/missing.pdf")
    assert exc_info.value.status_code == 404


def test_download_raises_on_http_403() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"forbidden")

    downloader = make_downloader(handler)
    with pytest.raises(DownloadHTTPError) as exc_info:
        downloader.download("https://example.org/forbidden.pdf")
    assert exc_info.value.status_code == 403


def test_download_raises_on_http_500() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"internal error")

    downloader = make_downloader(handler)
    with pytest.raises(DownloadHTTPError) as exc_info:
        downloader.download("https://example.org/error.pdf")
    assert exc_info.value.status_code == 500


def test_download_raises_on_file_too_large_via_content_length() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"x",
            headers={"content-type": "application/pdf", "content-length": "999999999"},
        )

    downloader = make_downloader(handler, max_size=1024)
    with pytest.raises(FileTooLargeError):
        downloader.download("https://example.org/big.pdf")


def test_download_raises_on_file_too_large_via_actual_bytes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"a" * 5000,
            headers={"content-type": "application/pdf"},
        )

    downloader = make_downloader(handler, max_size=1024)
    with pytest.raises(FileTooLargeError):
        downloader.download("https://example.org/big.pdf")


def test_download_raises_on_invalid_content_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html></html>",
            headers={"content-type": "text/plain"},
        )

    downloader = make_downloader(handler)
    with pytest.raises(InvalidContentTypeError):
        downloader.download("https://example.org/notes.txt")


def test_download_raises_on_missing_content_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=PDF_BYTES)

    downloader = make_downloader(handler)
    with pytest.raises(InvalidContentTypeError):
        downloader.download("https://example.org/paper.pdf")


def test_download_accepts_content_type_with_parameters() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=PDF_BYTES,
            headers={"content-type": "application/pdf; charset=binary"},
        )

    downloader = make_downloader(handler)
    result = downloader.download("https://example.org/paper.pdf")

    assert result.content_type == "application/pdf"


def test_download_accepts_custom_allowed_content_types() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"plain text",
            headers={"content-type": "text/plain"},
        )

    downloader = make_downloader(handler, allowed_content_types=["text/plain"])
    result = downloader.download("https://example.org/notes.txt")

    assert result.content_type == "text/plain"


def test_download_empty_response_is_allowed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"",
            headers={"content-type": "application/pdf"},
        )

    downloader = make_downloader(handler)
    result = downloader.download("https://example.org/empty.pdf")

    assert result.content == b""
    assert result.size == 0


def test_download_wraps_other_http_errors_as_download_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    downloader = make_downloader(handler)
    with pytest.raises(DownloadError):
        downloader.download("https://example.org/paper.pdf")


# --- SSRF protection (RDA-053) ---------------------------------------------


def _guard_with_resolver(resolver) -> SSRFGuard:
    return SSRFGuard(resolver=resolver)


def test_ssrf_guard_rejects_non_http_scheme() -> None:
    guard = _guard_with_resolver(lambda host: ["93.184.216.34"])
    with pytest.raises(SSRFBlockedError):
        guard.validate("ftp://example.org/paper.pdf")
    with pytest.raises(SSRFBlockedError):
        guard.validate("file:///etc/passwd")


def test_ssrf_guard_rejects_loopback() -> None:
    guard = _guard_with_resolver(lambda host: ["127.0.0.1"])
    with pytest.raises(SSRFBlockedError):
        guard.validate("http://localhost/paper.pdf")


def test_ssrf_guard_rejects_cloud_metadata_address() -> None:
    guard = _guard_with_resolver(lambda host: ["169.254.169.254"])
    with pytest.raises(SSRFBlockedError):
        guard.validate("http://169.254.169.254/latest/meta-data/")


def test_ssrf_guard_rejects_private_ipv4() -> None:
    guard = _guard_with_resolver(lambda host: ["10.0.0.5"])
    with pytest.raises(SSRFBlockedError):
        guard.validate("http://10.0.0.5/paper.pdf")


def test_ssrf_guard_rejects_private_ipv6() -> None:
    guard = _guard_with_resolver(lambda host: ["fd00::1"])
    with pytest.raises(SSRFBlockedError):
        guard.validate("http://[fd00::1]/paper.pdf")


def test_ssrf_guard_rejects_ipv4_mapped_ipv6() -> None:
    guard = _guard_with_resolver(lambda host: ["::ffff:127.0.0.1"])
    with pytest.raises(SSRFBlockedError):
        guard.validate("http://[::ffff:127.0.0.1]/paper.pdf")


def test_ssrf_guard_accepts_public_ip() -> None:
    guard = _guard_with_resolver(lambda host: ["93.184.216.34"])
    guard.validate("https://example.org/paper.pdf")


def test_ssrf_guard_rejects_when_any_resolved_address_is_blocked() -> None:
    guard = _guard_with_resolver(lambda host: ["93.184.216.34", "192.168.1.1"])
    with pytest.raises(SSRFBlockedError):
        guard.validate("https://example.org/paper.pdf")


def test_ssrf_guard_rejects_unresolvable_host() -> None:
    guard = _guard_with_resolver(lambda host: [])
    with pytest.raises(SSRFBlockedError):
        guard.validate("https://no-such-host.invalid/paper.pdf")


def test_download_rejects_blocked_url_before_any_request() -> None:
    """The downloader must not even attempt a request to a blocked URL."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("transport should not be called for a blocked URL")

    guard = _guard_with_resolver(lambda host: ["169.254.169.254"])
    downloader = make_downloader(handler, ssrf_guard=guard)
    with pytest.raises(SSRFBlockedError):
        downloader.download("http://169.254.169.254/latest/meta-data/")


# --- production path (no injected client) (RDA-056) ------------------------


def test_production_path_builds_client_with_max_redirects(monkeypatch) -> None:
    """Without an injected client the downloader must build an httpx.Client
    with the redirect cap, not call httpx.get() with unsupported kwargs."""

    captured: dict = {}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def get(self, url, **kwargs) -> httpx.Response:
            return httpx.Response(
                200,
                content=PDF_BYTES,
                headers={"content-type": "application/pdf"},
            )

    monkeypatch.setattr(httpx, "Client", FakeClient)
    downloader = DocumentDownloader(ssrf_guard=_PermissiveGuard())
    result = downloader.download("https://example.org/paper.pdf")

    assert captured["max_redirects"] == MAX_REDIRECTS
    assert captured["follow_redirects"] is True
    assert result.content == PDF_BYTES
