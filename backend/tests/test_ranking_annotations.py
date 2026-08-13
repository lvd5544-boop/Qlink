from copy import deepcopy
from pathlib import Path

import pytest

from app.ranking_annotations import (
    build_annotation_template,
    compare_annotations,
    validate_annotation,
)
from app.ranking_evaluation import load_ranking_dataset

DATASET_PATH = Path(__file__).resolve().parents[1] / "evaluation_data" / "ranking_eval_v1.json"


def _dataset():
    return load_ranking_dataset(DATASET_PATH)


def _completed_annotation(dataset, alias: str, seed: int):
    annotation = build_annotation_template(
        dataset,
        reviewer_alias=alias,
        pair_order_seed=seed,
    )
    queries = {query["id"]: query for query in dataset["queries"]}
    for label in annotation["labels"]:
        query = queries[label["query_id"]]
        label["relevance"] = query["relevance"][label["job_id"]]
        label["forbidden_cross_family"] = label["job_id"] in query["forbidden_job_ids"]
        label["rationale_source_fields"] = [
            "resume.expected_job_title",
            "job.title",
            "job.required_skills",
        ]
    annotation["independent_review_attestation"] = True
    return annotation


def test_template_is_shuffled_but_covers_every_pair_without_prefilled_labels():
    dataset = _dataset()
    first = build_annotation_template(dataset, reviewer_alias="reviewer-a", pair_order_seed=101)
    second = build_annotation_template(dataset, reviewer_alias="reviewer-b", pair_order_seed=202)

    expected_count = len(dataset["queries"]) * len(dataset["jobs"])
    assert len(first["labels"]) == expected_count == 33
    assert all(label["relevance"] is None for label in first["labels"])
    assert [(label["query_id"], label["job_id"]) for label in first["labels"]] != [
        (label["query_id"], label["job_id"]) for label in second["labels"]
    ]
    validate_annotation(first, dataset, require_complete=False)


def test_completed_annotation_requires_attestation_and_source_rationale():
    dataset = _dataset()
    annotation = _completed_annotation(dataset, "reviewer-a", 101)
    annotation["independent_review_attestation"] = False
    with pytest.raises(ValueError, match="attestation"):
        validate_annotation(annotation, dataset, require_complete=True)

    annotation["independent_review_attestation"] = True
    annotation["labels"][0]["rationale_source_fields"] = []
    with pytest.raises(ValueError, match="rationale source"):
        validate_annotation(annotation, dataset, require_complete=True)


def test_comparison_reports_weighted_agreement_and_adjudication_record():
    dataset = _dataset()
    reviewer_a = _completed_annotation(dataset, "reviewer-a", 101)
    reviewer_b = _completed_annotation(dataset, "reviewer-b", 202)
    changed = next(
        label
        for label in reviewer_b["labels"]
        if label["query_id"] == "query-backend" and label["job_id"] == "job-platform-cloud"
    )
    changed["relevance"] = 2
    changed["reviewer_notes"] = "Relevant, but not as direct as payments backend."

    result = compare_annotations(reviewer_a, reviewer_b, dataset)

    assert result["pair_count"] == 33
    assert result["exact_relevance_agreement"] == pytest.approx(32 / 33, abs=1e-6)
    assert 0 < result["quadratic_weighted_kappa"] < 1
    assert result["forbidden_label_agreement"] == 1
    assert result["disagreement_count"] == 1
    assert result["adjudication_status"] == "pending"
    disagreement = result["disagreements"][0]
    assert disagreement["query_id"] == "query-backend"
    assert disagreement["job_id"] == "job-platform-cloud"
    assert disagreement["adjudicated_relevance"] is None


def test_comparison_rejects_same_reviewer_alias():
    dataset = _dataset()
    reviewer_a = _completed_annotation(dataset, "reviewer-a", 101)
    reviewer_b = deepcopy(reviewer_a)
    with pytest.raises(ValueError, match="distinct reviewer aliases"):
        compare_annotations(reviewer_a, reviewer_b, dataset)
