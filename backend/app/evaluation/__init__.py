"""Evaluation datasets and helpers for the Research Discovery Agent."""

from app.evaluation.benchmark import BenchmarkDataset, BenchmarkQuestion, load_benchmark
from app.evaluation.evidence import (
	ClaimEvidenceStatus,
	EvidenceEvaluationResult,
	EvidenceEvaluator,
	evaluate_evidence,
	write_evaluation_report,
)

__all__ = [
	"BenchmarkDataset",
	"BenchmarkQuestion",
	"ClaimEvidenceStatus",
	"EvidenceEvaluationResult",
	"EvidenceEvaluator",
	"evaluate_evidence",
	"load_benchmark",
	"write_evaluation_report",
]