"""Independent annotation templates and agreement metrics for ranking evaluation."""

from __future__ import annotations

import random
from collections import Counter
from copy import deepcopy
from typing import Any

RELEVANCE_LEVELS = (0, 1, 2, 3)
ANNOTATION_SCHEMA_VERSION = "ranking-annotation-v1"


def build_annotation_template(
    dataset: dict[str, Any],
    *,
    reviewer_alias: str,
    pair_order_seed: int,
) -> dict[str, Any]:
    alias = reviewer_alias.strip()
    if not alias:
        raise ValueError("reviewer_alias is required")
    pairs = [
        {
            "query_id": query["id"],
            "job_id": job["id"],
            "relevance": None,
            "forbidden_cross_family": None,
            "rationale_source_fields": [],
            "reviewer_notes": "",
        }
        for query in dataset["queries"]
        for job in dataset["jobs"]
    ]
    random.Random(pair_order_seed).shuffle(pairs)
    return {
        "schema_version": ANNOTATION_SCHEMA_VERSION,
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["version"],
        "reviewer_alias": alias,
        "pair_order_seed": pair_order_seed,
        "independent_review_attestation": False,
        "instructions": (
            "Complete labels without viewing model scores or another reviewer's file, "
            "then set independent_review_attestation to true."
        ),
        "labels": pairs,
    }


def _expected_pairs(dataset: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (str(query["id"]), str(job["id"]))
        for query in dataset["queries"]
        for job in dataset["jobs"]
    }


def validate_annotation(
    annotation: dict[str, Any],
    dataset: dict[str, Any],
    *,
    require_complete: bool,
) -> dict[tuple[str, str], dict[str, Any]]:
    if annotation.get("schema_version") != ANNOTATION_SCHEMA_VERSION:
        raise ValueError("annotation schema version does not match")
    if annotation.get("dataset_id") != dataset.get("dataset_id"):
        raise ValueError("annotation dataset id does not match")
    if annotation.get("dataset_version") != dataset.get("version"):
        raise ValueError("annotation dataset version does not match")
    if not str(annotation.get("reviewer_alias") or "").strip():
        raise ValueError("reviewer_alias is required")
    if require_complete and annotation.get("independent_review_attestation") is not True:
        raise ValueError("completed annotation requires independent review attestation")

    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for label in annotation.get("labels") or []:
        key = (str(label.get("query_id") or ""), str(label.get("job_id") or ""))
        if key in indexed:
            raise ValueError(f"duplicate annotation pair: {key}")
        indexed[key] = label

        relevance = label.get("relevance")
        forbidden = label.get("forbidden_cross_family")
        sources = label.get("rationale_source_fields")
        if require_complete:
            if type(relevance) is not int or relevance not in RELEVANCE_LEVELS:
                raise ValueError(f"{key} relevance must be an integer from 0 to 3")
            if type(forbidden) is not bool:
                raise ValueError(f"{key} forbidden_cross_family must be boolean")
            if forbidden and relevance != 0:
                raise ValueError(f"{key} forbidden pairs must have relevance 0")
            if not isinstance(sources, list) or not any(str(value).strip() for value in sources):
                raise ValueError(f"{key} needs at least one rationale source field")

    expected = _expected_pairs(dataset)
    if set(indexed) != expected:
        missing = sorted(expected - set(indexed))
        extra = sorted(set(indexed) - expected)
        raise ValueError(
            f"annotation pair coverage mismatch; missing={missing[:3]} extra={extra[:3]}"
        )
    return indexed


def _quadratic_weighted_kappa(left: list[int], right: list[int]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("kappa requires two non-empty equally sized label lists")
    size = len(RELEVANCE_LEVELS)
    count = len(left)
    left_counts = Counter(left)
    right_counts = Counter(right)
    observed = 0.0
    expected = 0.0
    maximum_distance = float((size - 1) ** 2)
    for first in RELEVANCE_LEVELS:
        for second in RELEVANCE_LEVELS:
            weight = ((first - second) ** 2) / maximum_distance
            observed_count = sum(
                1
                for left_value, right_value in zip(left, right, strict=True)
                if left_value == first and right_value == second
            )
            observed += weight * observed_count / count
            expected += weight * (left_counts[first] * right_counts[second]) / (count * count)
    if expected == 0:
        return 1.0 if observed == 0 else 0.0
    return 1.0 - observed / expected


def compare_annotations(
    reviewer_a: dict[str, Any],
    reviewer_b: dict[str, Any],
    dataset: dict[str, Any],
) -> dict[str, Any]:
    alias_a = str(reviewer_a.get("reviewer_alias") or "").strip()
    alias_b = str(reviewer_b.get("reviewer_alias") or "").strip()
    if alias_a == alias_b:
        raise ValueError("independent comparison requires distinct reviewer aliases")
    labels_a = validate_annotation(reviewer_a, dataset, require_complete=True)
    labels_b = validate_annotation(reviewer_b, dataset, require_complete=True)

    ordered_pairs = sorted(labels_a)
    relevance_a = [int(labels_a[key]["relevance"]) for key in ordered_pairs]
    relevance_b = [int(labels_b[key]["relevance"]) for key in ordered_pairs]
    exact_relevance = sum(
        first == second for first, second in zip(relevance_a, relevance_b, strict=True)
    )
    exact_forbidden = sum(
        labels_a[key]["forbidden_cross_family"] == labels_b[key]["forbidden_cross_family"]
        for key in ordered_pairs
    )
    disagreements = []
    for key in ordered_pairs:
        first = labels_a[key]
        second = labels_b[key]
        if (
            first["relevance"] == second["relevance"]
            and first["forbidden_cross_family"] == second["forbidden_cross_family"]
        ):
            continue
        disagreements.append(
            {
                "query_id": key[0],
                "job_id": key[1],
                "reviewer_a": {
                    "relevance": first["relevance"],
                    "forbidden_cross_family": first["forbidden_cross_family"],
                    "rationale_source_fields": deepcopy(first["rationale_source_fields"]),
                    "reviewer_notes": first.get("reviewer_notes") or "",
                },
                "reviewer_b": {
                    "relevance": second["relevance"],
                    "forbidden_cross_family": second["forbidden_cross_family"],
                    "rationale_source_fields": deepcopy(second["rationale_source_fields"]),
                    "reviewer_notes": second.get("reviewer_notes") or "",
                },
                "adjudicated_relevance": None,
                "adjudicated_forbidden_cross_family": None,
                "adjudication_rationale": "",
            }
        )

    pair_count = len(ordered_pairs)
    return {
        "schema_version": "ranking-annotation-comparison-v1",
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["version"],
        "reviewers": [alias_a, alias_b],
        "pair_count": pair_count,
        "exact_relevance_agreement": round(exact_relevance / pair_count, 6),
        "quadratic_weighted_kappa": round(_quadratic_weighted_kappa(relevance_a, relevance_b), 6),
        "forbidden_label_agreement": round(exact_forbidden / pair_count, 6),
        "disagreement_count": len(disagreements),
        "adjudication_status": "pending" if disagreements else "not_required",
        "disagreements": disagreements,
    }
