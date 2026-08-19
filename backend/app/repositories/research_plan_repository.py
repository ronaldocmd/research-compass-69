"""Data access for the `research_plans` table (RDA-031)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.plan import ResearchPlanRecord


class ResearchPlanRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, **values: object) -> ResearchPlanRecord:
        plan = ResearchPlanRecord(**values)
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def get(self, plan_id: uuid.UUID) -> ResearchPlanRecord | None:
        return self.db.get(ResearchPlanRecord, plan_id)

    def get_by_research_id(self, research_id: uuid.UUID) -> ResearchPlanRecord | None:
        stmt = (
            select(ResearchPlanRecord)
            .where(ResearchPlanRecord.research_id == research_id)
            .order_by(ResearchPlanRecord.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def list_by_research_id(self, research_id: uuid.UUID) -> list[ResearchPlanRecord]:
        stmt = (
            select(ResearchPlanRecord)
            .where(ResearchPlanRecord.research_id == research_id)
            .order_by(ResearchPlanRecord.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars())

    def delete(self, plan: ResearchPlanRecord) -> None:
        self.db.delete(plan)
        self.db.commit()

    def delete_by_research_id(self, research_id: uuid.UUID) -> None:
        for plan in self.list_by_research_id(research_id):
            self.db.delete(plan)
        self.db.commit()
