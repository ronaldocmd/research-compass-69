"""Data access for the `researches` table (RDA-006).

Only this layer touches the database; the Service layer depends on it.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.research import Research


class ResearchRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, **values: object) -> Research:
        research = Research(**values)
        self.db.add(research)
        self.db.commit()
        self.db.refresh(research)
        return research

    def list(self, *, limit: int = 50, offset: int = 0) -> list[Research]:
        stmt = (
            select(Research)
            .order_by(Research.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.execute(stmt).scalars())

    def get(self, research_id: uuid.UUID) -> Research | None:
        return self.db.get(Research, research_id)

    def update(self, research: Research, **values: object) -> Research:
        for field, value in values.items():
            setattr(research, field, value)
        self.db.commit()
        self.db.refresh(research)
        return research

    def delete(self, research: Research) -> None:
        self.db.delete(research)
        self.db.commit()
