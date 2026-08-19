"""Document downloader package (RDA-018).

    URL -> DocumentDownloader.download() -> DownloadResult (raw bytes + metadata)

Parsing, storage and further processing are later tickets.
"""

from app.services.downloader.downloader import DocumentDownloader
from app.services.downloader.schemas import DownloadResult

__all__ = ["DocumentDownloader", "DownloadResult"]
