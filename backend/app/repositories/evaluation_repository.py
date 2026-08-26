"""Data access for the `human_evaluations` table (RDA-049).

Evaluations are append-only: creating a new one never deletes or overwrites
older ratings, so inter-rater agreement can be computed later.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.human_evaluation import HumanEvaluation
from app.schemas.evaluation import HumanEvaluationCreate


class EvaluationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_evaluation(self, data: HumanEvaluationCreate) -> HumanEvaluation:
        evaluation = HumanEvaluation(
            claim_id=data.claim_id,
            research_id=data.research_id,
            evaluator_id=data.evaluator_id,
            rating=data.rating,
            comment=data.comment,
        )
        self.db.add(evaluation)
        self.db.commit()
        self.db.refresh(evaluation)
        return evaluation

    def get_by_claim(self, claim_id: uuid.UUID) -> list[HumanEvaluation]:
        stmt = (
            select(HumanEvaluation)
            .where(HumanEvaluation.claim_id == claim_id)
            .order_by(HumanEvaluation.evaluated_at.asc())
        )
        return list(self.db.execute(stmt).scalars())

    def get_by_research(self, research_id: uuid.UUID) -> list[HumanEvaluation]:
        stmt = (
            select(HumanEvaluation)
            .where(HumanEvaluation.research_id == research_id)
            .order_by(HumanEvaluation.evaluated_at.asc())
        )
        return list(self.db.execute(stmt).scalars())

    def get_statistics(self, research_id: uuid.UUID) -> dict:
        """Return the simple rating distribution for one research.

        Percentages are 0..1. When there are no evaluations all rates are 0.0.
        """
        rows = self.db.execute(
            select(HumanEvaluation.rating, func.count())
            .where(HumanEvaluation.research_id == research_id)
            .group_by(HumanEvaluation.rating)
        ).all()
        counts = {rating: count for rating, count in rows}
        total = sum(counts.values())
        if total == 0:
            return {"total": 0, "correct": 0.0, "incorrect": 0.0, "inconclusive": 0.0}
        return {
            "total": total,
            "correct": counts.get("correct", 0) / total,
            "incorrect": counts.get("incorrect", 0) / total,
            "inconclusive": counts.get("inconclusive", 0) / total,
        }
