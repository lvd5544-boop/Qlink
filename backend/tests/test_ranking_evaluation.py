from copy import deepcopy
from pathlib import Path

import pytest

from app.ranking_evaluation import (
    candidate_document,
    load_ranking_dataset,
    rank_structured,
    rank_tfidf,
    run_ranking_evaluation,
    validate_ranking_dataset,
)

DATASET_PATH = Path(__file__).resolve().parents[1] / "evaluation_data" / "ranking_eval_v1.json"


def _dataset():
    return load_ranking_dataset(DATASET_PATH)


def test_fixed_dataset_grades_every_job_and_forbidden_examples_are_irrelevant():
    dataset = _dataset()
    job_ids = {job["id"] for job in dataset["jobs"]}
    for query in dataset["queries"]:
        assert set(query["relevance"]) == job_ids
        assert all(query["relevance"][job_id] == 0 for job_id in query["forbidden_job_ids"])


def test_dataset_validation_rejects_incomplete_relevance_labels():
    dataset = deepcopy(_dataset())
    dataset["queries"][0]["relevance"].pop("job-clinical-nurse")
    with pytest.raises(ValueError, match="grade every job"):
        validate_ranking_dataset(dataset)


def test_tfidf_candidate_document_excludes_identity_school_and_employer_brand():
    profile = _dataset()["queries"][0]["profile"]
    document = candidate_document(profile)
    assert profile["name"] not in document
    assert profile["school"] not in document
    assert profile["work_experience"][0]["company"] not in document
    assert "Backend Software Engineer" in document
    assert "FastAPI" in document


def test_both_rankers_are_deterministic_and_return_every_job():
    dataset = _dataset()
    expected_count = len(dataset["jobs"])
    for ranker in (rank_tfidf, rank_structured):
        first = ranker(dataset)
        second = ranker(dataset)
        assert first == second
        assert all(len(items) == expected_count for items in first.values())


def test_c4_e_metrics_and_counterfactual_gate_are_reproducible():
    dataset = _dataset()
    result = run_ranking_evaluation(dataset, k=3)
    assert set(result["models"]) == {
        "tfidf_cosine",
        "structured_human_preference_v3",
    }
    for metrics in result["models"].values():
        assert 0 <= metrics["ndcg_at_k"] <= 1
        assert 0 <= metrics["recall_at_k"] <= 1
        assert 0 <= metrics["cross_family_violation_rate_at_k"] <= 1
        assert metrics["unsupported_negative_judgment_rate"] == 0
        assert 0 <= metrics["explanation_citation_coverage"] <= 1
        assert metrics["query_count"] == 3
        assert metrics["evaluated_pairs"] == len(dataset["queries"]) * len(dataset["jobs"])

    fairness = result["counterfactual_fairness"]
    assert fairness["tfidf_cosine"]["passed"] is True
    assert fairness["structured_human_preference_v3"]["passed"] is True


def test_c4_e_robustness_cases_cover_and_pass_four_fixed_stress_types():
    result = run_ranking_evaluation(_dataset(), k=3)
    expected_types = {
        "multilingual_paraphrase",
        "missing_fields",
        "preference_conflict",
        "near_title_decoy",
    }
    for model in result["robustness"].values():
        assert model["case_count"] == 4
        assert {case["type"] for case in model["cases"]} == expected_types
    structured = result["robustness"]["structured_human_preference_v3"]
    assert structured["passed"] is True
    assert all(case["forbidden_hits_at_k"] == [] for case in structured["cases"])

    tfidf = result["robustness"]["tfidf_cosine"]
    assert tfidf["passed"] is False
    failed = [case for case in tfidf["cases"] if not case["passed"]]
    assert [case["type"] for case in failed] == ["preference_conflict"]
    assert failed[0]["forbidden_hits_at_k"] == ["job-backend-fintech"]


def test_what_changed_the_ranking_names_changed_and_unchanged_inputs():
    change = run_ranking_evaluation(_dataset())["what_changed_the_ranking"]
    assert change["available"] is True
    assert change["changed_input"] == "match_preferences"
    assert "skills" in change["unchanged_inputs"]
    assert change["movements"]
    assert change["top_before"] != change["top_after"]
    assert "job-data-analyst-finance" not in change["top_after"]
