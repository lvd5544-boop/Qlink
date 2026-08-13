from pathlib import Path

from app.hypothesis_evaluation import (
    load_hypothesis_dataset,
    run_hypothesis_evaluation,
)
from app.ranking_evaluation import load_ranking_dataset, run_ranking_evaluation

ROOT = Path(__file__).resolve().parents[2]
EVALUATION_DATA = ROOT / "backend" / "evaluation_data"


def test_public_case_study_and_workflow_visual_match_reproducible_results():
    ranking_dataset = load_ranking_dataset(EVALUATION_DATA / "ranking_eval_v1.json")
    ranking = run_ranking_evaluation(ranking_dataset, k=3)
    hypothesis_dataset = load_hypothesis_dataset(
        EVALUATION_DATA / "hypothesis_eval_synthetic_v1.json",
        expected_pool="synthetic",
    )
    hypothesis = run_hypothesis_evaluation(hypothesis_dataset)

    case_study = (ROOT / "docs" / "PROJECT_CASE_STUDY.md").read_text(encoding="utf-8")
    visual = (ROOT / "docs" / "assets" / "qlink-evidence-workflow.svg").read_text(encoding="utf-8")
    public_artifacts = f"{case_study}\n{visual}"

    structured = ranking["models"]["structured_human_preference_v3"]
    tfidf = ranking["models"]["tfidf_cosine"]
    pair_count = len(ranking_dataset["queries"]) * len(ranking_dataset["jobs"])
    annotation = ranking_dataset["annotation_status"]

    assert str(pair_count) in public_artifacts
    assert f"{structured['ndcg_at_k']:.3f}" in public_artifacts
    assert f"{tfidf['ndcg_at_k']:.3f}" in public_artifacts
    assert f"{structured['cross_family_violation_rate_at_k']:.3f}" in public_artifacts
    assert f"{hypothesis['sample_count']} / {hypothesis['sample_count']}" in visual
    assert f"real-confirmed samples used: {hypothesis['real_confirmed_samples_used']}" in visual
    assert (
        f"{annotation['completed_independent_reviewers']} / "
        f"{annotation['required_independent_reviewers']}" in visual
    )
    assert "pending 0/2" in case_study


def test_public_application_language_keeps_unfinished_external_validation_explicit():
    talk_track = (ROOT / "docs" / "APPLICATION_TALK_TRACK.md").read_text(encoding="utf-8")
    pilot = (ROOT / "docs" / "C6_PILOT_PROTOCOL.md").read_text(encoding="utf-8")

    assert "pending 0/2" in talk_track
    assert "20-user pilot completed" in talk_track
    assert "protocol ready; recruitment pending; no real-user effectiveness claim" in pilot
