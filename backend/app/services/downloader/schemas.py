"""DTOs for the document downloader (RDA-018)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DownloadResult(BaseModel):
    """A successfully downloaded document payload and its metadata."""

    model_config = ConfigDict(extra="forbid")

    content: bytes
    content_type: str
    size: int
    downloaded_at: datetime
    source_url: str
