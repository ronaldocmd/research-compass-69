"""Validated benchmark dataset primitives (RDA-046)."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BenchmarkQuestion(BaseModel):
    """One research question and its reproducible evaluation targets."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    language: str = Field(default="pt", min_length=2, max_length=10)
    depth: Literal["superficial", "medium", "deep"]
    expected_sources: list[str] | None = None
    evaluation_criteria: list[str] = Field(min_length=1)


class BenchmarkDataset(BaseModel):
    """A versioned collection of benchmark cases."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    created_at: datetime
    questions: list[BenchmarkQuestion] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_case_ids(self) -> "BenchmarkDataset":
        ids = [question.id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark case IDs must be unique")
        return self


BenchmarkCase = BenchmarkQuestion


def load_benchmark(version: str | Path = "v1.0") -> BenchmarkDataset:
    """Load a versioned benchmark dataset from ``backend/data/benchmarks``."""
    benchmark_path = Path(version)
    if not benchmark_path.exists():
        benchmark_path = Path(__file__).parents[2] / "data" / "benchmarks" / f"{version}.json"
    raw = benchmark_path.read_text(encoding="utf-8")
    payload: dict[str, Any] = json.loads(raw)
    return BenchmarkDataset.model_validate(payload)