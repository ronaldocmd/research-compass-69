"""ORM models registered on Base.metadata (Alembic autogenerate target)."""

from app.models.document import Document, DocumentStatus
from app.models.research import Research, ResearchStatus

__all__ = ["Research", "ResearchStatus", "Document", "DocumentStatus"]
