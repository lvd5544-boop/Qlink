from __future__ import annotations

from app.matching import _evaluate_hybrid
from app.matching_preference import (
    apply_preference_policy,
    infer_candidate_intent,
    infer_job_industries,
)


DATA_RESUME = {
    "name": "Lin",
    "skills": [
        {"name": "Python"},
        {"name": "pandas"},
        {"name": "scikit-learn"},
    ],
    "projects": [{
        "name": "Air Quality Forecasting",
        "description": (
            "Compared random forest and regression models using R² and MSE "
            "for real-time air quality forecasting."
        ),
    }],
}


def test_candidate_intent_uses_projects_and_skills_when_title_is_missing():
    intent = infer_candidate_intent(DATA_RESUME)

    assert intent["primary_role"] == "data_ai"
    assert intent["confidence"] >= 0.6


def test_cross_role_sports_job_is_not_eligible_for_data_candidate():
    score, breakdown, reason = _evaluate_hybrid(
        DATA_RESUME,
        {
            "title": "Sports and Recreation Coordinator",
            "responsibilities": [
                "Plan recreation programs, manage community sports events, and coordinate facilities."
            ],
            "required_skills": [],
        },
        "Sports and Recreation Coordinator",
    )

    policy = breakdown["preference_policy"]
    assert breakdown["source"] == "human_preference_v3"
    assert policy["eligible"] is False
    assert policy["job_role"]["primary_role"] == "hospitality_recreation"
    assert score <= 2.5
    assert "不进入精准推荐" in reason


def test_data_job_passes_and_explicit_industry_exclusion_wins():
    job = {
        "title": "Data Scientist",
        "company_name": "Fintech Lab",
        "responsibilities": ["Build machine learning models for payment risk."],
        "required_skills": [{"name": "Python"}, {"name": "machine learning"}],
    }
    score, breakdown, _ = _evaluate_hybrid(DATA_RESUME, job, "Data Scientist")
    assert breakdown["preference_policy"]["eligible"] is True
    assert score > 2.5

    excluded_resume = {
        **DATA_RESUME,
        "match_preferences": {
            "target_roles": ["Data Scientist"],
            "excluded_industries": ["finance"],
            "strictness": "focused",
        },
    }
    gated, gated_breakdown, _ = apply_preference_policy(
        excluded_resume, job, "Data Scientist", 7.0, {}
    )
    assert gated_breakdown["preference_policy"]["eligible"] is False
    assert gated <= 2.5


def test_broken_page_title_is_filtered_even_if_body_has_skill_words():
    score, breakdown, _ = _evaluate_hybrid(
        DATA_RESUME,
        {"title": "PUSHDOWN", "responsibilities": ["Python SQL"], "required_skills": []},
        "PUSHDOWN",
    )
    assert breakdown["preference_policy"]["eligible"] is False
    assert breakdown["preference_policy"]["quality_passed"] is False
    assert score <= 2.5


def test_incidental_jd_words_do_not_become_job_industries():
    job = {
        "title": "Data Scientist - Cybersecurity Analyst",
        "company_name": "Security Lab",
        "responsibilities": [
            "We offer a fun work environment and monitor social media threats."
        ],
    }

    assert infer_job_industries(job, job["title"]) == ["technology"]
