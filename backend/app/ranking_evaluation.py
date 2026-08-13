"""Deterministic offline evaluation for candidate-visible job recommendations.

The evaluator deliberately excludes names, schools, and employer names from the
TF-IDF baseline. It compares that text-only baseline with the production
human-preference hybrid scorer without writing application data or calling an
external model.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from .matching import evaluate_hybrid_match

EVALUATOR_VERSION = "c4-e-v1.3"
DEFAULT_RELEVANCE_THRESHOLD = 2
UNSUPPORTED_NEGATIVE_PATTERNS = (
    re.compile(r"\b(?:lacks?|unqualified|incapable)\b", re.IGNORECASE),
    re.compile(r"不具备|不能胜任|能力不足|缺\s"),
)


def load_ranking_dataset(path: str | Path) -> dict[str, Any]:
    dataset = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_ranking_dataset(dataset)
    return dataset


def validate_ranking_dataset(dataset: dict[str, Any]) -> None:
    jobs = dataset.get("jobs") or []
    queries = dataset.get("queries") or []
    job_ids = [str(item.get("id") or "") for item in jobs]
    query_ids = [str(item.get("id") or "") for item in queries]
    if not dataset.get("dataset_id") or not dataset.get("version"):
        raise ValueError("dataset_id and version are required")
    if not jobs or not queries:
        raise ValueError("the evaluation set needs jobs and queries")
    if any(not value for value in job_ids) or len(job_ids) != len(set(job_ids)):
        raise ValueError("job ids must be non-empty and unique")
    if any(not value for value in query_ids) or len(query_ids) != len(set(query_ids)):
        raise ValueError("query ids must be non-empty and unique")

    expected_jobs = set(job_ids)
    for query in queries:
        relevance = query.get("relevance") or {}
        if set(relevance) != expected_jobs:
            raise ValueError(f"{query['id']} must grade every job exactly once")
        forbidden = set(query.get("forbidden_job_ids") or [])
        if not forbidden <= expected_jobs:
            raise ValueError(f"{query['id']} references an unknown forbidden job")
        if any(int(relevance[job_id]) != 0 for job_id in forbidden):
            raise ValueError(f"{query['id']} forbidden jobs must have relevance 0")

    known_queries = set(query_ids)
    robustness_ids: set[str] = set()
    for case in dataset.get("robustness_cases") or []:
        case_id = str(case.get("id") or "")
        if not case_id or case_id in robustness_ids:
            raise ValueError("robustness case ids must be non-empty and unique")
        robustness_ids.add(case_id)
        if case.get("base_query_id") not in known_queries:
            raise ValueError(f"{case_id} references an unknown base query")
        if int(case.get("k") or 0) <= 0:
            raise ValueError(f"{case_id} needs a positive k")
        if int(case.get("minimum_expected_hits_at_k") or 0) <= 0:
            raise ValueError(f"{case_id} needs a positive expected-hit threshold")
        additional_ids = {str(job.get("id") or "") for job in case.get("additional_jobs") or []}
        available_ids = expected_jobs | additional_ids
        referenced_ids = set(case.get("expected_top_job_ids") or []) | set(
            case.get("forbidden_job_ids") or []
        )
        if not referenced_ids <= available_ids:
            raise ValueError(f"{case_id} references an unknown job")


def _plain_list(values: list[Any] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        if isinstance(value, dict):
            text = value.get("name") or value.get("title") or ""
        else:
            text = value
        if str(text).strip():
            result.append(str(text).strip())
    return result


def candidate_document(profile: dict[str, Any]) -> str:
    """Build ranking text without identity, school, or employer-brand fields."""
    parts = [
        str(profile.get("expected_job_title") or ""),
        str(profile.get("summary") or ""),
        " ".join(_plain_list(profile.get("skills"))),
        " ".join(_plain_list(profile.get("soft_skills"))),
    ]
    for experience in profile.get("work_experience") or []:
        if isinstance(experience, dict):
            parts.extend(
                [
                    str(experience.get("position") or ""),
                    str(experience.get("description") or ""),
                ]
            )
    for project in profile.get("projects") or []:
        if isinstance(project, dict):
            parts.extend(
                [
                    str(project.get("role") or ""),
                    str(project.get("description") or ""),
                ]
            )
    return " ".join(value for value in parts if value).strip()


def job_document(profile: dict[str, Any]) -> str:
    """Build job text without company name so brand prestige cannot affect rank."""
    parts = [
        str(profile.get("title") or ""),
        str(profile.get("description") or ""),
        str(profile.get("industry") or ""),
        " ".join(_plain_list(profile.get("required_skills"))),
        " ".join(str(value) for value in profile.get("responsibilities") or []),
    ]
    return " ".join(value for value in parts if value).strip()


def tokenize_for_tfidf(text: str) -> list[str]:
    lowered = str(text or "").casefold()
    english = re.findall(r"[a-z0-9][a-z0-9+#.\-]*", lowered)
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", lowered)
    chinese: list[str] = []
    for run in chinese_runs:
        chinese.extend(run)
        chinese.extend(run[index : index + 2] for index in range(len(run) - 1))
    return english + chinese


def _idf(documents: list[list[str]]) -> dict[str, float]:
    document_frequency: Counter[str] = Counter()
    for tokens in documents:
        document_frequency.update(set(tokens))
    count = len(documents)
    return {
        token: math.log((1 + count) / (1 + frequency)) + 1
        for token, frequency in document_frequency.items()
    }


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = sum(counts.values())
    raw = {token: (count / total) * idf.get(token, 0.0) for token, count in counts.items()}
    norm = math.sqrt(sum(value * value for value in raw.values()))
    if not norm:
        return {}
    return {token: value / norm for token, value in raw.items()}


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    shared = set(left) & set(right)
    return sum(left[token] * right[token] for token in shared)


def _unsafe_negative_claims(reason: str) -> list[str]:
    return [pattern.pattern for pattern in UNSUPPORTED_NEGATIVE_PATTERNS if pattern.search(reason)]


def rank_tfidf(
    dataset: dict[str, Any],
    profile_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    profile_overrides = profile_overrides or {}
    jobs = dataset["jobs"]
    query_profiles = []
    for query in dataset["queries"]:
        profile = deepcopy(query["profile"])
        profile.update(deepcopy(profile_overrides.get(query["id"]) or {}))
        query_profiles.append(profile)

    job_tokens = [tokenize_for_tfidf(job_document(job["profile"])) for job in jobs]
    query_tokens = [tokenize_for_tfidf(candidate_document(profile)) for profile in query_profiles]
    idf = _idf(job_tokens + query_tokens)
    job_vectors = [_tfidf_vector(tokens, idf) for tokens in job_tokens]

    rankings: dict[str, list[dict[str, Any]]] = {}
    for query, tokens in zip(dataset["queries"], query_tokens, strict=True):
        query_vector = _tfidf_vector(tokens, idf)
        ranked = []
        for job, vector, tokens_for_job in zip(jobs, job_vectors, job_tokens, strict=True):
            matched_terms = sorted(set(tokens) & set(tokens_for_job))
            ranked.append(
                {
                    "job_id": job["id"],
                    "score": round(_cosine(query_vector, vector), 8),
                    "reason": "shared TF-IDF terms",
                    "explanation_claims": [
                        {
                            "claim": "text similarity is based on shared normalized terms",
                            "citations": ["candidate_document", "job_document"]
                            if matched_terms
                            else [],
                        }
                    ],
                    "matched_terms": matched_terms[:12],
                    "unsupported_negative_claims": [],
                }
            )
        rankings[query["id"]] = sorted(ranked, key=lambda item: (-item["score"], item["job_id"]))
    return rankings


def _structured_explanation_claims(breakdown: dict[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    skills = breakdown.get("skills") or {}
    if skills.get("matched"):
        claims.append(
            {
                "claim": "required skills appear in the candidate material",
                "citations": ["resume.skills", "job.required_skills"],
            }
        )
    policy = breakdown.get("preference_policy") or {}
    if policy.get("role_relation"):
        claims.append(
            {
                "claim": f"role relation is {policy['role_relation']}",
                "citations": ["resume.expected_job_title", "job.title"],
            }
        )
    if policy.get("industry_overlap"):
        claims.append(
            {
                "claim": "candidate and job industry preferences overlap",
                "citations": ["resume.match_preferences", "job.industry"],
            }
        )
    if not claims:
        claims.append({"claim": "structured score has no cited positive factor", "citations": []})
    return claims


def rank_structured(
    dataset: dict[str, Any],
    profile_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    profile_overrides = profile_overrides or {}
    rankings: dict[str, list[dict[str, Any]]] = {}
    for query in dataset["queries"]:
        profile = deepcopy(query["profile"])
        profile.update(deepcopy(profile_overrides.get(query["id"]) or {}))
        ranked = []
        for job in dataset["jobs"]:
            job_profile = job["profile"]
            score, breakdown, reason = evaluate_hybrid_match(
                profile, job_profile, str(job_profile.get("title") or "")
            )
            ranked.append(
                {
                    "job_id": job["id"],
                    "score": round(float(score), 8),
                    "reason": reason,
                    "eligible": bool(
                        (breakdown.get("preference_policy") or {}).get("eligible", True)
                    ),
                    "breakdown": breakdown,
                    "explanation_claims": _structured_explanation_claims(breakdown),
                    "unsupported_negative_claims": _unsafe_negative_claims(reason),
                }
            )
        rankings[query["id"]] = sorted(ranked, key=lambda item: (-item["score"], item["job_id"]))
    return rankings


def _dcg(relevances: list[int]) -> float:
    return sum(
        (2**relevance - 1) / math.log2(index + 2) for index, relevance in enumerate(relevances)
    )


def _round_metric(value: float) -> float:
    return round(float(value), 6)


def evaluate_rankings(
    dataset: dict[str, Any],
    rankings: dict[str, list[dict[str, Any]]],
    *,
    k: int = 3,
    relevance_threshold: int = DEFAULT_RELEVANCE_THRESHOLD,
) -> dict[str, Any]:
    per_query = []
    forbidden_hits = 0
    top_slots = 0
    cited_claims = 0
    explanation_claims = 0
    unsupported_claims = 0
    evaluated_pairs = 0

    for query in dataset["queries"]:
        ranked = rankings[query["id"]]
        visible_ranked = [item for item in ranked if item.get("eligible", True)]
        graded = query["relevance"]
        cutoff = min(k, len(visible_ranked))
        actual = [int(graded[item["job_id"]]) for item in visible_ranked[:cutoff]]
        ideal = sorted((int(value) for value in graded.values()), reverse=True)[:cutoff]
        ideal_dcg = _dcg(ideal)
        ndcg = _dcg(actual) / ideal_dcg if ideal_dcg else 0.0
        relevant_ids = {
            job_id for job_id, grade in graded.items() if int(grade) >= relevance_threshold
        }
        retrieved_relevant = sum(
            1 for item in visible_ranked[:cutoff] if item["job_id"] in relevant_ids
        )
        recall = retrieved_relevant / len(relevant_ids) if relevant_ids else 0.0
        query_forbidden_hits = sum(
            1 for item in visible_ranked[:cutoff] if item["job_id"] in query["forbidden_job_ids"]
        )
        forbidden_hits += query_forbidden_hits
        top_slots += cutoff

        for item in ranked:
            evaluated_pairs += 1
            unsupported_claims += len(item.get("unsupported_negative_claims") or [])
            for claim in item.get("explanation_claims") or []:
                explanation_claims += 1
                if claim.get("citations"):
                    cited_claims += 1

        per_query.append(
            {
                "query_id": query["id"],
                "ndcg_at_k": _round_metric(ndcg),
                "recall_at_k": _round_metric(recall),
                "forbidden_hits_at_k": query_forbidden_hits,
                "returned_at_k": cutoff,
                "top_job_ids": [item["job_id"] for item in visible_ranked[:cutoff]],
            }
        )

    count = len(per_query)
    return {
        "ndcg_at_k": _round_metric(sum(item["ndcg_at_k"] for item in per_query) / count),
        "recall_at_k": _round_metric(sum(item["recall_at_k"] for item in per_query) / count),
        "cross_family_violation_rate_at_k": _round_metric(
            forbidden_hits / top_slots if top_slots else 0.0
        ),
        "unsupported_negative_judgment_rate": _round_metric(
            unsupported_claims / evaluated_pairs if evaluated_pairs else 0.0
        ),
        "explanation_citation_coverage": _round_metric(
            cited_claims / explanation_claims if explanation_claims else 0.0
        ),
        "query_count": count,
        "evaluated_pairs": evaluated_pairs,
        "k": k,
        "per_query": per_query,
    }


def evaluate_counterfactual_stability(
    dataset: dict[str, Any],
    ranker: Callable[..., dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    original = ranker(dataset)
    overrides = {
        query["id"]: query.get("counterfactual_overrides") or {} for query in dataset["queries"]
    }
    changed = ranker(dataset, overrides)
    per_query = []
    for query in dataset["queries"]:
        query_id = query["id"]
        before = original[query_id]
        after = changed[query_id]
        before_scores = {item["job_id"]: item["score"] for item in before}
        after_scores = {item["job_id"]: item["score"] for item in after}
        max_delta = max(
            abs(before_scores[job_id] - after_scores[job_id]) for job_id in before_scores
        )
        stable_order = [item["job_id"] for item in before] == [item["job_id"] for item in after]
        per_query.append(
            {
                "query_id": query_id,
                "stable_order": stable_order,
                "max_score_delta": _round_metric(max_delta),
            }
        )
    return {
        "passed": all(item["stable_order"] and item["max_score_delta"] == 0 for item in per_query),
        "changed_fields": ["name", "school"],
        "per_query": per_query,
    }


def explain_ranking_change(dataset: dict[str, Any]) -> dict[str, Any]:
    case = dataset.get("ranking_change_case") or {}
    query_id = case.get("query_id")
    if not query_id:
        return {"available": False}
    before = [item for item in rank_structured(dataset)[query_id] if item.get("eligible", True)]
    after = [
        item
        for item in rank_structured(dataset, {query_id: case.get("profile_overrides") or {}})[
            query_id
        ]
        if item.get("eligible", True)
    ]
    before_positions = {item["job_id"]: index + 1 for index, item in enumerate(before)}
    after_positions = {item["job_id"]: index + 1 for index, item in enumerate(after)}
    movements = [
        {
            "job_id": job_id,
            "rank_before": before_positions.get(job_id),
            "rank_after": after_positions.get(job_id),
            "change": (
                "entered"
                if job_id not in before_positions
                else ("left" if job_id not in after_positions else "moved")
            ),
            "rank_delta": (
                before_positions[job_id] - after_positions[job_id]
                if job_id in before_positions and job_id in after_positions
                else None
            ),
        }
        for job_id in sorted(set(before_positions) | set(after_positions))
        if before_positions.get(job_id) != after_positions.get(job_id)
    ]
    movements.sort(
        key=lambda item: (
            item["change"] != "entered",
            item["change"] != "left",
            -abs(item["rank_delta"] or 0),
            item["job_id"],
        )
    )
    return {
        "available": True,
        "query_id": query_id,
        "changed_input": "match_preferences",
        "unchanged_inputs": ["skills", "experience", "projects", "education"],
        "description": case.get("description"),
        "top_before": [item["job_id"] for item in before[:3]],
        "top_after": [item["job_id"] for item in after[:3]],
        "movements": movements,
    }


def evaluate_robustness_cases(
    dataset: dict[str, Any],
    ranker: Callable[..., dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    results = []
    for case in dataset.get("robustness_cases") or []:
        case_dataset = deepcopy(dataset)
        case_dataset["jobs"].extend(deepcopy(case.get("additional_jobs") or []))
        query_id = str(case["base_query_id"])
        rankings = ranker(
            case_dataset,
            {query_id: deepcopy(case.get("profile_overrides") or {})},
        )[query_id]
        visible = [item for item in rankings if item.get("eligible", True)]
        cutoff = min(int(case["k"]), len(visible))
        top_ids = [item["job_id"] for item in visible[:cutoff]]
        expected = set(case.get("expected_top_job_ids") or [])
        forbidden = set(case.get("forbidden_job_ids") or [])
        expected_hits = len(expected & set(top_ids))
        forbidden_hits = sorted(forbidden & set(top_ids))
        minimum_hits = int(case["minimum_expected_hits_at_k"])
        results.append(
            {
                "case_id": case["id"],
                "type": case["type"],
                "passed": expected_hits >= minimum_hits and not forbidden_hits,
                "expected_hits_at_k": expected_hits,
                "minimum_expected_hits_at_k": minimum_hits,
                "forbidden_hits_at_k": forbidden_hits,
                "returned_at_k": cutoff,
                "top_job_ids": top_ids,
            }
        )
    return {
        "passed": bool(results) and all(item["passed"] for item in results),
        "case_count": len(results),
        "cases": results,
    }


def run_ranking_evaluation(dataset: dict[str, Any], *, k: int = 3) -> dict[str, Any]:
    tfidf = rank_tfidf(dataset)
    structured = rank_structured(dataset)
    return {
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["version"],
        "evaluator_version": EVALUATOR_VERSION,
        "configuration": {
            "k": k,
            "relevance_threshold": DEFAULT_RELEVANCE_THRESHOLD,
            "external_model_calls": False,
            "identity_fields_excluded": ["name", "school", "company_name"],
        },
        "annotation_status": deepcopy(dataset.get("annotation_status") or {}),
        "models": {
            "tfidf_cosine": evaluate_rankings(dataset, tfidf, k=k),
            "structured_human_preference_v3": evaluate_rankings(dataset, structured, k=k),
        },
        "counterfactual_fairness": {
            "tfidf_cosine": evaluate_counterfactual_stability(dataset, rank_tfidf),
            "structured_human_preference_v3": evaluate_counterfactual_stability(
                dataset, rank_structured
            ),
        },
        "robustness": {
            "tfidf_cosine": evaluate_robustness_cases(dataset, rank_tfidf),
            "structured_human_preference_v3": evaluate_robustness_cases(dataset, rank_structured),
        },
        "what_changed_the_ranking": explain_ranking_change(dataset),
        "limitations": [
            "The dataset is synthetic and intentionally small; metrics do not estimate hiring outcomes.",
            "Relevance grades are product test labels, not employer decisions or candidate quality labels.",
            "Counterfactual coverage is limited to identity and school-name fields in this version.",
        ],
    }
