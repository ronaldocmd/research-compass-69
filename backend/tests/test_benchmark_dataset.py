"""Tests for the RDA-046 benchmark dataset contract."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation.benchmark import BenchmarkDataset, load_benchmark


DATASET = Path(__file__).parents[1] / "data" / "benchmark.jsonl"


def test_repository_benchmark_loads_and_has_unique_cases() -> None:
    dataset = load_benchmark(DATASET)

    assert dataset.name == "benchmark"
    assert dataset.version == "1"
    assert len(dataset.cases) == 3
    assert len({case.id for case in dataset.cases}) == len(dataset.cases)
    assert all(case.expected_claims for case in dataset.cases)


def test_json_benchmark_loads_with_metadata(tmp_path: Path) -> None:
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps({
            "name": "test", "version": "2026-08", "cases": [{
                "id": "case-1", "question": "Question?", "expected_claims": ["Claim."],
            }]
        }),
        encoding="utf-8",
    )

    dataset = load_benchmark(path)

    assert dataset.name == "test"
    assert dataset.cases[0].expected_sources == []


def test_duplicate_case_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        BenchmarkDataset(
            name="test",
            version="1",
            cases=[
                {"id": "same", "question": "one", "expected_claims": ["a"]},
                {"id": "same", "question": "two", "expected_claims": ["b"]},
            ],
        )