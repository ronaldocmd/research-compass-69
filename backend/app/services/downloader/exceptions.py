"""Domain exceptions for the document downloader (RDA-018).

Follows the same convention as app.services.search.exceptions: a base
class plus specific subclasses, so callers can catch the base type and
still distinguish concrete failure modes.
"""


class DownloadError(Exception):
    """Base class for every error raised by DocumentDownloader."""


class DownloadTimeoutError(DownloadError):
    """The request to the source URL timed out."""


class DownloadHTTPError(DownloadError):
    """The source responded with a non-2xx HTTP status."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class FileTooLargeError(DownloadError):
    """The response exceeds the configured maximum download size."""


class InvalidContentTypeError(DownloadError):
    """The response Content-Type is not an allowed document type."""
