"""Data access for the `plan_tasks` table (RDA-031)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.plan import PlanTaskRecord


class PlanTaskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, **values: object) -> PlanTaskRecord:
        task = PlanTaskRecord(**values)
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def bulk_create(self, tasks_data: list[dict]) -> list[PlanTaskRecord]:
        tasks = [PlanTaskRecord(**values) for values in tasks_data]
        self.db.add_all(tasks)
        self.db.commit()
        for task in tasks:
            self.db.refresh(task)
        return tasks

    def get(self, task_id: uuid.UUID) -> PlanTaskRecord | None:
        return self.db.get(PlanTaskRecord, task_id)

    def list_by_plan_id(self, plan_id: uuid.UUID) -> list[PlanTaskRecord]:
        stmt = (
            select(PlanTaskRecord)
            .where(PlanTaskRecord.plan_id == plan_id)
            .order_by(PlanTaskRecord.priority.asc(), PlanTaskRecord.order.asc())
        )
        return list(self.db.execute(stmt).scalars())
