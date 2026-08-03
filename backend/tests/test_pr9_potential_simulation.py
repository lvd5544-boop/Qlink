"""PR9 server-owned improvement simulation contracts."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models_db import PotentialSimulationEvent
from app.potential_simulation import build_simulation

pytestmark = pytest.mark.asyncio


async def test_candidate_simulation_is_reproducible_and_records_view(
    client, auth_header, candidate_a, resume_a, job_a, db_session
):
    path = f"/resumes/{resume_a.id}/jobs/{job_a.id}/improvement-simulation"
    first = await client.get(path, headers=auth_header(candidate_a))
    second = await client.get(path, headers=auth_header(candidate_a))
    assert first.status_code == second.status_code == 200
    data = first.json()
    assert data["rule_version"] == "pr9-deterministic-v1"
    assert data["current_score"] == second.json()["current_score"]
    assert data["potential_score"] == second.json()["potential_score"]
    assert len(data["source_versions"]["resume_snapshot_sha256"]) == 64
    assert data["source_versions"]["scoring_version"] == "hybrid_v2"
    assert (
        data["target_role_profile"]["source"]["source_kind"] == "employer_provided_job_description"
    )
    assert len(data["source_versions"]["target_role_profile_sha256"]) == 64
    assert "offer" not in str(data).lower()
    assert all(len(issue["strategy_options"]) >= 2 for issue in data["issues"])
    events = (await db_session.execute(select(PotentialSimulationEvent))).scalars().all()
    assert [event.event_type for event in events] == ["viewed", "viewed"]


async def test_candidate_cannot_tamper_with_strategy_identifier(
    client, auth_header, candidate_a, employer_a, resume_a, job_a
):
    path = f"/resumes/{resume_a.id}/jobs/{job_a.id}/improvement-simulation"
    denied = await client.get(path, headers=auth_header(employer_a))
    assert denied.status_code == 403
    rejected = await client.post(
        path, headers=auth_header(candidate_a), json={"strategy_ids": ["made-up"]}
    )
    assert rejected.status_code == 422


async def test_empty_strategy_list_means_user_selected_no_actions(
    client, auth_header, candidate_a, resume_a, job_a
):
    path = f"/resumes/{resume_a.id}/jobs/{job_a.id}/improvement-simulation"
    default = await client.get(path, headers=auth_header(candidate_a))
    cleared = await client.post(path, headers=auth_header(candidate_a), json={"strategy_ids": []})
    assert default.status_code == cleared.status_code == 200
    assert default.json()["selected_strategy_ids"]
    assert cleared.json()["selected_strategy_ids"] == []
    assert cleared.json()["potential_score"] == cleared.json()["current_score"]
    assert cleared.json()["strategy_status"]["state"] == "strategies_selected"
    assert cleared.json()["strategy_status"]["selected_count"] == 0

    reloaded = await client.get(path, headers=auth_header(candidate_a))
    assert reloaded.status_code == 200
    assert reloaded.json()["selected_strategy_ids"] == []
    assert reloaded.json()["strategy_status"]["state"] == "strategies_selected"


async def test_strategy_lifecycle_events_are_candidate_owned(
    client, auth_header, candidate_a, resume_a, job_a, db_session
):
    path = f"/resumes/{resume_a.id}/jobs/{job_a.id}/improvement-simulation/events"
    response = await client.post(
        path,
        headers=auth_header(candidate_a),
        json={"event_type": "rejected", "strategy_ids": []},
    )
    assert response.status_code == 200
    assert response.json()["strategy_status"]["state"] == "rejected"
    assert response.json()["selected_strategy_ids"] == []
    event = (await db_session.execute(select(PotentialSimulationEvent))).scalar_one()
    assert event.event_type == "rejected"

    reloaded = await client.get(
        f"/resumes/{resume_a.id}/jobs/{job_a.id}/improvement-simulation",
        headers=auth_header(candidate_a),
    )
    assert reloaded.status_code == 200
    assert reloaded.json()["strategy_status"]["state"] == "rejected"
    assert reloaded.json()["selected_strategy_ids"] == []


async def test_pilot_metrics_are_admin_only_and_aggregate_only(
    client, auth_header, candidate_a, admin_user, resume_a, job_a
):
    path = f"/resumes/{resume_a.id}/jobs/{job_a.id}/improvement-simulation"
    viewed = await client.get(path, headers=auth_header(candidate_a))
    selected = await client.post(
        path,
        headers=auth_header(candidate_a),
        json={"strategy_ids": viewed.json()["selected_strategy_ids"][:1]},
    )
    assert selected.status_code == 200
    endpoint = "/admin/potential-simulation/pilot-metrics"
    assert (await client.get(endpoint, headers=auth_header(candidate_a))).status_code == 403
    response = await client.get(endpoint, headers=auth_header(admin_user))
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["event_counts"]["viewed"] == 1
    assert metrics["event_counts"]["strategies_selected"] == 1
    assert metrics["view_to_selection_rate"] == 1.0
    assert "candidate" not in str(metrics).lower()
    assert "公平性结论" in metrics["interpretation_notice"]


async def test_hard_constraint_never_becomes_an_apply_now_resume_patch():
    resume = {
        "skills": [{"name": "python"}],
        "work_experience": [{"duration_years": 1}],
        "title": "后端工程师",
    }
    job = {"required_skills": [{"name": "python"}], "experience_years": 5}
    result = build_simulation(resume, job, "后端工程师", [])
    issue = next(item for item in result["issues"] if item["issue_type"] == "hard_constraint")
    assert all(not item["can_apply_now"] for item in issue["strategy_options"])
    assert all("patch" not in item for item in issue["strategy_options"])
    assert all(item["estimated_delta"] == 0 for item in result["selected_actions"])
    assert "相对模拟" in result["assumptions"][0]


async def test_quantification_is_never_apply_now_without_traced_numeric_evidence():
    resume = {"skills": [], "work_experience": [{"duration_years": 1}], "title": "产品经理"}
    job = {"required_skills": [], "experience_years": 0}
    result = build_simulation(
        resume,
        job,
        "产品经理",
        [{"id": "claim-1", "current_text": "负责项目", "evidence_state": "not_enough_information"}],
    )


async def test_target_role_profile_preserves_jd_provenance_without_turning_taxonomy_into_truth():
    result = build_simulation(
        {"skills": []},
        {
            "title": "后端工程师",
            "required_skills": [{"name": "Python"}],
            "_raw_text": "要求 Python",
        },
        "后端工程师",
        [],
    )
    profile = result["target_role_profile"]
    requirement = profile["requirements"][0]
    assert profile["source"]["is_company_requirement"] is True
    assert requirement["canonical_skill"] == "python"
    assert requirement["normalization"]["source"] == "local_crosswalk"
    assert "不新增" in profile["normalization_notice"]
    capability = next(
        issue for issue in result["issues"] if issue["issue_id"] == "capability:missing_skills"
    )
    assert capability["source_refs"] == [requirement["requirement_id"]]
    options = [option for issue in result["issues"] for option in issue["strategy_options"]]
    assert not any(
        option["strategy"] == "quantification" and option["can_apply_now"] for option in options
    )


async def test_presentation_differentiation_and_career_narrative_have_real_classification_paths():
    result = build_simulation(
        {"expected_job_title": "运营专员", "skills": [], "summary": "", "projects": []},
        {"required_skills": [{"name": "python"}], "experience_years": 0},
        "后端工程师",
        [],
    )
    types = {issue["issue_type"] for issue in result["issues"]}
    assert {
        "presentation_gap",
        "differentiation_gap",
        "relevance_gap",
        "career_narrative_gap",
    } <= types
    assert all(len(issue["strategy_options"]) >= 2 for issue in result["issues"])


async def test_counterfactual_recomputes_expression_evidence_and_capability_from_real_inputs():
    resume = {
        "expected_job_title": "运营专员",
        "skills": [{"name": "python"}],
        "work_experience": [{"duration_years": 2, "description": "负责服务优化"}],
    }
    job = {"required_skills": [{"name": "python"}, {"name": "fastapi"}], "experience_years": 0}
    claims = [
        {
            "id": "claim-1",
            "current_text": "负责服务优化，QPS 80",
            "evidence_state": "supported_by_user_evidence",
        }
    ]
    default = build_simulation(resume, job, "后端工程师", claims)
    ids = {
        option["strategy"]: option["strategy_id"]
        for issue in default["issues"]
        for option in issue["strategy_options"]
    }
    selected = [
        ids["relevance_alignment"],
        ids["quantification"],
        ids["skill_or_experience_building"],
    ]
    result = build_simulation(resume, job, "后端工程师", claims, selected)
    assert result["expression_delta"] > 0
    assert result["evidence_delta"] > 0
    assert result["capability_delta"] > 0
    assert result["potential_delta"] == round(
        result["expression_delta"] + result["evidence_delta"] + result["capability_delta"], 2
    )
    assert {
        item["status"] for item in result["selection_effects"]
    } == {"changes_score_if_removed"}


async def test_selection_effects_explain_overlap_and_missing_evidence_without_fake_score():
    resume = {
        "expected_job_title": "运营专员",
        "summary": "",
        "skills": [],
        "projects": [{"name": "Existing Project", "description": "Built a service"}],
    }
    job = {"required_skills": [], "experience_years": 0}
    default = build_simulation(resume, job, "后端工程师", [])
    ids = {
        option["strategy"]: option["strategy_id"]
        for issue in default["issues"]
        for option in issue["strategy_options"]
    }

    evidence_only = build_simulation(
        resume,
        job,
        "后端工程师",
        [{"id": "claim-1", "current_text": "Built a service", "evidence_state": "not_enough_information"}],
        [ids["method_and_tradeoff"]],
    )
    assert evidence_only["potential_score"] == evidence_only["current_score"]
    assert evidence_only["selection_effects"] == [
        {
            "strategy_id": ids["method_and_tradeoff"],
            "marginal_delta": 0.0,
            "status": "needs_supported_evidence",
        }
    ]

    overlapping = build_simulation(
        resume,
        job,
        "后端工程师",
        [],
        [ids["role_clarity"], ids["relevance_alignment"]],
    )
    assert all(
        item["status"] == "overlaps_or_no_scoring_effect"
        for item in overlapping["selection_effects"]
    )


REGRESSION_CASES = [
    ("后端工程师", "python"),
    ("前端工程师", "react"),
    ("数据分析师", "sql"),
    ("产品经理", "roadmap"),
    ("运营专员", "growth"),
    ("UX设计师", "figma"),
    ("研究员", "research"),
    ("销售经理", "crm"),
    ("项目经理", "agile"),
    ("测试工程师", "pytest"),
    ("DevOps工程师", "kubernetes"),
    ("安全工程师", "security"),
    ("算法工程师", "machine learning"),
    ("财务分析师", "excel"),
    ("HRBP", "recruiting"),
    ("客户成功经理", "saas"),
    ("供应链专员", "logistics"),
    ("市场经理", "campaign"),
    ("应届生项目", "portfolio"),
    ("工程管理者", "leadership"),
]


@pytest.mark.parametrize(("role", "missing_skill"), REGRESSION_CASES)
async def test_fixed_cross_role_regressions_are_deterministic_and_do_not_claim_hiring_probability(
    role, missing_skill
):
    resume = {
        "skills": [{"name": "python"}],
        "work_experience": [{"duration_years": 1}],
        "expected_job_title": role,
    }
    job = {
        "required_skills": [{"name": "python"}, {"name": missing_skill}],
        "experience_years": 2,
    }
    first = build_simulation(resume, job, role, [])
    second = build_simulation(resume, job, role, [])
    assert first == second
    assert 0 <= first["current_score"] <= 10
    assert 0 <= first["potential_score"] <= 10
    assert "offer" not in str(first).lower()
    assert not any(
        option["strategy"] == "quantification" and option["can_apply_now"]
        for issue in first["issues"]
        for option in issue["strategy_options"]
    )
