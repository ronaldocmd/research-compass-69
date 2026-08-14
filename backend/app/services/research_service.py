"""Business rules for Research (RDA-006).

Raises ResearchNotFoundError; the API layer maps it to HTTP 404 so the
service stays framework-agnostic.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.research import Research
from app.repositories.research_repository import ResearchRepository
from app.schemas.research import ResearchCreate, ResearchUpdate


class ResearchNotFoundError(Exception):
    """Raised when a Research id does not exist."""

    def __init__(self, research_id: uuid.UUID) -> None:
        super().__init__(f"Research {research_id} not found")
        self.research_id = research_id


class ResearchService:
    def __init__(self, db: Session) -> None:
        self.repository = ResearchRepository(db)

    def create(self, payload: ResearchCreate) -> Research:
        return self.repository.create(**payload.model_dump())

    def list(self, *, limit: int = 50, offset: int = 0) -> list[Research]:
        return self.repository.list(limit=limit, offset=offset)

    def get(self, research_id: uuid.UUID) -> Research:
        research = self.repository.get(research_id)
        if research is None:
            raise ResearchNotFoundError(research_id)
        return research

    def update(self, research_id: uuid.UUID, payload: ResearchUpdate) -> Research:
        research = self.get(research_id)
        values = payload.model_dump(exclude_unset=True)
        if not values:
            return research
        return self.repository.update(research, **values)

    def delete(self, research_id: uuid.UUID) -> None:
        self.repository.delete(self.get(research_id))
