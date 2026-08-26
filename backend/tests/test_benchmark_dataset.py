"""Tests for the RDA-046 benchmark dataset contract."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation.benchmark import BenchmarkDataset, load_benchmark


DATASET = Path(__file__).parents[1] / "data" / "benchmarks" / "v1.0.json"


def test_repository_benchmark_loads_and_has_unique_cases() -> None:
    dataset = load_benchmark()

    assert dataset.version == "v1.0"
    assert len(dataset.questions) == 6
    assert len({question.id for question in dataset.questions}) == len(dataset.questions)
    assert all(question.evaluation_criteria for question in dataset.questions)


def test_json_benchmark_loads_with_metadata(tmp_path: Path) -> None:
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps({
            "version": "test", "created_at": "2026-08-26T00:00:00Z", "questions": [{
                "id": "case-1", "question": "Question?", "objective": "Objective.", "depth": "medium", "evaluation_criteria": ["Criterion."],
            }]
        }),
        encoding="utf-8",
    )

    dataset = load_benchmark(path)

    assert dataset.version == "test"
    assert dataset.questions[0].expected_sources is None


def test_duplicate_case_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        BenchmarkDataset(
            version="v1.0",
            created_at="2026-08-26T00:00:00Z",
            questions=[
                {"id": "same", "question": "one", "objective": "a", "depth": "medium", "evaluation_criteria": ["criterion"]},
                {"id": "same", "question": "two", "objective": "b", "depth": "medium", "evaluation_criteria": ["criterion"]},
            ],
        )