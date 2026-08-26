"""Validated benchmark dataset primitives (RDA-046)."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BenchmarkCase(BaseModel):
    """One deterministic research question and its evaluation targets."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_claims: list[str] = Field(min_length=1)
    expected_sources: list[str] = Field(default_factory=list)
    required_keywords: list[str] = Field(default_factory=list)


class BenchmarkDataset(BaseModel):
    """A versioned collection of benchmark cases."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    cases: list[BenchmarkCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_case_ids(self) -> "BenchmarkDataset":
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark case IDs must be unique")
        return self


def load_benchmark(path: str | Path) -> BenchmarkDataset:
    """Load a JSON or JSONL benchmark file and validate its contract."""
    benchmark_path = Path(path)
    raw = benchmark_path.read_text(encoding="utf-8")
    if benchmark_path.suffix.lower() == ".jsonl":
        payload: dict[str, Any] = {"cases": [json.loads(line) for line in raw.splitlines() if line.strip()]}
        payload.setdefault("name", benchmark_path.stem)
        payload.setdefault("version", "1")
    else:
        payload = json.loads(raw)
    return BenchmarkDataset.model_validate(payload)