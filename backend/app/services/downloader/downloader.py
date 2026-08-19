"""DocumentDownloader service (RDA-018).

Downloads a document from a URL and returns the raw bytes plus metadata,
without parsing, storing or otherwise processing the content (those are
later tickets). Uses the same synchronous httpx.Client pattern as the
search providers (RDA-012/RDA-013), so it can be injected with a
MockTransport in tests.
"""

from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.services.downloader.exceptions import (
    DownloadError,
    DownloadHTTPError,
    DownloadTimeoutError,
    FileTooLargeError,
    InvalidContentTypeError,
)
from app.services.downloader.schemas import DownloadResult


class DocumentDownloader:
    """Downloads a document's raw bytes from its source URL."""

    def __init__(
        self,
        *,
        timeout: float | None = None,
        max_size: int | None = None,
        allowed_content_types: list[str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._timeout = timeout if timeout is not None else settings.DOWNLOAD_TIMEOUT_SECONDS
        self._max_size = max_size if max_size is not None else settings.DOWNLOAD_MAX_SIZE_BYTES
        self._allowed_content_types = [
            ct.strip().lower()
            for ct in (
                allowed_content_types
                if allowed_content_types is not None
                else settings.DOWNLOAD_ALLOWED_CONTENT_TYPES.split(",")
            )
        ]
        self._client = client

    def download(self, url: str) -> DownloadResult:
        """Download ``url`` and return its raw bytes plus metadata.

        Args:
            url: The source URL of the document.

        Returns:
            DownloadResult with content bytes, content_type, size,
            downloaded_at and source_url.

        Raises:
            DownloadTimeoutError: The request timed out.
            DownloadHTTPError: The source returned a non-2xx status.
            FileTooLargeError: The response exceeds the max size.
            InvalidContentTypeError: The Content-Type is not allowed.
            DownloadError: Any other transport failure.
        """
        try:
            if self._client is not None:
                response = self._client.get(url, timeout=self._timeout)
            else:
                response = httpx.get(url, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            raise DownloadTimeoutError(f"Download timed out for {url}") from exc
        except httpx.HTTPError as exc:
            raise DownloadError(f"Download failed for {url}: {exc}") from exc

        if response.status_code >= 400:
            raise DownloadHTTPError(
                response.status_code,
                f"Download returned HTTP {response.status_code} for {url}",
            )

        content_type = self._extract_content_type(response)
        self._validate_content_type(content_type)

        content_length = self._content_length(response)
        if content_length is not None and content_length > self._max_size:
            raise FileTooLargeError(
                f"Content-Length {content_length} exceeds max size {self._max_size}"
            )

        content = response.content
        if len(content) > self._max_size:
            raise FileTooLargeError(
                f"Downloaded {len(content)} bytes exceeds max size {self._max_size}"
            )

        return DownloadResult(
            content=content,
            content_type=content_type,
            size=len(content),
            downloaded_at=datetime.now(timezone.utc),
            source_url=url,
        )

    @staticmethod
    def _extract_content_type(response: httpx.Response) -> str:
        raw = response.headers.get("content-type", "")
        return raw.split(";")[0].strip().lower()

    def _validate_content_type(self, content_type: str) -> None:
        if not content_type:
            raise InvalidContentTypeError("Response has no Content-Type header")
        if content_type not in self._allowed_content_types:
            raise InvalidContentTypeError(
                f"Content-Type {content_type!r} is not allowed"
            )

    @staticmethod
    def _content_length(response: httpx.Response) -> int | None:
        raw = response.headers.get("content-length")
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            return None
