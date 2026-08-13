"""Offline C5 evaluation with strict synthetic/real-confirmed pool separation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .inference_hypotheses import build_issue_hypotheses

FORBIDDEN_SYNTHETIC_KEYS = frozenset(
    {
        "user_id",
        "resume_id",
        "application_id",
        "candidate_id",
        "email",
        "phone",
        "name",
    }
)


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


def load_hypothesis_dataset(path: Path, *, expected_pool: str) -> dict[str, Any]:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if dataset.get("pool_kind") != expected_pool:
        raise ValueError("evaluation pool mismatch")
    samples = dataset.get("samples")
    if not isinstance(samples, list):
        raise ValueError("evaluation samples must be a list")
    if expected_pool == "synthetic":
        forbidden = _keys(dataset) & FORBIDDEN_SYNTHETIC_KEYS
        if forbidden:
            raise ValueError(f"synthetic pool contains identity keys: {sorted(forbidden)}")
        if any(not str(sample.get("id", "")).startswith("synthetic-") for sample in samples):
            raise ValueError("synthetic sample ids must use the synthetic- prefix")
    if expected_pool == "real_confirmed" and samples:
        raise ValueError("real confirmed samples must remain in the external consented store")
    return dataset


def run_hypothesis_evaluation(dataset: dict[str, Any]) -> dict[str, Any]:
    if dataset.get("pool_kind") != "synthetic":
        raise ValueError("only the isolated synthetic pool can run in repository CI")
    results = []
    for sample in dataset["samples"]:
        hypotheses = build_issue_hypotheses(
            issue_type=sample["issue_type"],
            target_requirement_id=sample.get("target_requirement_id"),
            source_refs=sample.get("source_refs") or [],
        )
        count = len(hypotheses)
        passed = sample["expected_min_hypotheses"] <= count <= sample["expected_max_hypotheses"]
        passed = passed and count <= 2 and all(item["source_refs"] for item in hypotheses)
        results.append({"sample_id": sample["id"], "hypothesis_count": count, "passed": passed})
    return {
        "dataset_id": dataset["dataset_id"],
        "pool_kind": "synthetic",
        "sample_count": len(results),
        "passed": all(item["passed"] for item in results),
        "real_confirmed_samples_used": 0,
        "results": results,
    }
