from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models_db import (
    JobDescription,
    OptimizationIssue,
    ResumePatchProposal,
    ResumeVersion,
)

pytestmark = pytest.mark.asyncio


def _headers(auth_header, user, key):
    return {**auth_header(user), "Idempotency-Key": key}


async def _diagnose(client, candidate_a, resume_a, job_a, auth_header, key="pr13-diag"):
    return await client.post(
        f"/resumes/{resume_a.id}/jobs/{job_a.id}/diagnostics",
        headers=_headers(auth_header, candidate_a, key),
    )


async def test_diagnostic_requires_owned_resume_and_target_job(
    client, candidate_a, resume_b, job_a, auth_header
):
    response = await client.post(
        f"/resumes/{resume_b.id}/jobs/{job_a.id}/diagnostics",
        headers=_headers(auth_header, candidate_a, "pr13-owned"),
    )
    assert response.status_code == 404

    missing = await client.post(
        f"/resumes/{resume_b.id}/jobs/{uuid.uuid4()}/diagnostics",
        headers=_headers(auth_header, candidate_a, "pr13-missing-job"),
    )
    assert missing.status_code == 404


async def test_diagnostic_rejects_another_candidates_private_import(
    client, db_session, candidate_a, candidate_b, resume_a, auth_header
):
    private_job = JobDescription(
        employer_id=None,
        title="候选人 B 的私有目标岗位",
        raw_text="Python 后端工程师",
        parsed_json={
            "advisor_private": True,
            "advisor_imported_by": str(candidate_b.id),
            "required_skills": ["Python"],
        },
    )
    db_session.add(private_job)
    await db_session.commit()
    await db_session.refresh(private_job)

    response = await client.post(
        f"/resumes/{resume_a.id}/jobs/{private_job.id}/diagnostics",
        headers=_headers(auth_header, candidate_a, "pr13-private-job"),
    )

    assert response.status_code == 404


async def test_diagnostic_persists_multiple_categorized_issues_without_credibility_score(
    client, db_session, candidate_a, resume_a, job_a, auth_header
):
    response = await _diagnose(client, candidate_a, resume_a, job_a, auth_header)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["issues"]) >= 2
    assert set(payload["categories"]) == {
        "expression",
        "evidence",
        "capability",
        "hard_constraint",
        "consistency",
        "structure_ats",
        "relevance",
        "differentiation",
        "career_narrative",
        "privacy_compliance",
    }
    assert "credibility_score" not in str(payload)
    assert payload["readiness"]["current"] >= 0
    assert payload["readiness"]["future_scenario"] >= 0
    rows = (
        (
            await db_session.execute(
                select(OptimizationIssue).where(
                    OptimizationIssue.diagnostic_id == payload["diagnostic_id"]
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == len(payload["issues"])


async def test_rewrite_uses_candidate_claims_not_jd_and_requires_confirmation(
    client, candidate_a, resume_a, job_a, auth_header
):
    diagnostic = (
        await _diagnose(client, candidate_a, resume_a, job_a, auth_header, "pr13-rewrite-diag")
    ).json()
    issue = next(item for item in diagnostic["issues"] if item["claim_ids"])
    strategy = issue["strategies"][0]
    preview = await client.post(
        f"/optimization/issues/{issue['id']}/rewrite-preview",
        json={"strategy_id": strategy["id"]},
        headers=_headers(auth_header, candidate_a, "pr13-preview"),
    )
    assert preview.status_code == 200, preview.text
    proposal = preview.json()
    assert proposal["source_claim_ids"]
    assert proposal["status"] == "needs_confirmation"
    assert proposal["fidelity_status"] == "ready"
    assert job_a.raw_text not in proposal["after_text"]

    blocked = await client.post(
        f"/resume-patches/{proposal['id']}/apply",
        headers=_headers(auth_header, candidate_a, "pr13-apply-too-early"),
    )
    assert blocked.status_code == 409


async def test_apply_rechecks_fidelity_and_blocks_tampered_new_facts(
    client, db_session, candidate_a, resume_a, job_a, auth_header
):
    diagnostic = (
        await _diagnose(client, candidate_a, resume_a, job_a, auth_header, "pr13-tamper-diag")
    ).json()
    issue = next(item for item in diagnostic["issues"] if item["claim_ids"])
    preview = await client.post(
        f"/optimization/issues/{issue['id']}/rewrite-preview",
        json={"strategy_id": issue["strategies"][0]["id"]},
        headers=_headers(auth_header, candidate_a, "pr13-tamper-preview"),
    )
    proposal_id = preview.json()["id"]
    confirmed = await client.post(
        f"/resume-patches/{proposal_id}/confirm-facts",
        headers=_headers(auth_header, candidate_a, "pr13-tamper-confirm"),
    )
    assert confirmed.status_code == 200

    row = await db_session.get(ResumePatchProposal, proposal_id)
    row.after_text = f"{row.after_text}；主导 Kubernetes 项目并提升 99%"
    await db_session.commit()
    blocked = await client.post(
        f"/resume-patches/{proposal_id}/apply",
        headers=_headers(auth_header, candidate_a, "pr13-tamper-apply"),
    )
    assert blocked.status_code == 409
    assert "Fidelity" in blocked.json()["detail"]


async def test_apply_creates_new_resume_version_without_overwriting_history(
    client, db_session, candidate_a, resume_a, job_a, auth_header
):
    diagnostic = (
        await _diagnose(client, candidate_a, resume_a, job_a, auth_header, "pr13-apply-diag")
    ).json()
    issue = next(item for item in diagnostic["issues"] if item["claim_ids"])
    preview = await client.post(
        f"/optimization/issues/{issue['id']}/rewrite-preview",
        json={"strategy_id": issue["strategies"][0]["id"]},
        headers=_headers(auth_header, candidate_a, "pr13-apply-preview"),
    )
    proposal = preview.json()
    confirmed = await client.post(
        f"/resume-patches/{proposal['id']}/confirm-facts",
        headers=_headers(auth_header, candidate_a, "pr13-apply-confirm"),
    )
    assert confirmed.status_code == 200
    applied = await client.post(
        f"/resume-patches/{proposal['id']}/apply",
        headers=_headers(auth_header, candidate_a, "pr13-apply"),
    )
    assert applied.status_code == 200, applied.text
    result = applied.json()
    assert result["resume_version"]["parent_version_id"] == diagnostic["resume_version_id"]
    versions = (
        (
            await db_session.execute(
                select(ResumeVersion)
                .where(ResumeVersion.resume_id == str(resume_a.id))
                .order_by(ResumeVersion.version_number)
            )
        )
        .scalars()
        .all()
    )
    assert len(versions) == 2
    assert versions[0].id == diagnostic["resume_version_id"]
    assert versions[0].parsed_json_snapshot["summary"] == proposal["before_text"]
    assert versions[1].parsed_json_snapshot["summary"] == proposal["after_text"]


async def test_completed_future_action_does_not_raise_current_readiness(
    client, candidate_a, resume_a, job_a, auth_header
):
    diagnostic = (
        await _diagnose(client, candidate_a, resume_a, job_a, auth_header, "pr13-action-diag")
    ).json()
    issue = diagnostic["issues"][0]
    strategy = issue["strategies"][0]
    selected = await client.post(
        f"/optimization/issues/{issue['id']}/select-strategy",
        json={"strategy_id": strategy["id"]},
        headers=_headers(auth_header, candidate_a, "pr13-action-select"),
    )
    assert selected.status_code == 200, selected.text
    action_id = selected.json()["action"]["id"]
    before = await client.get(
        f"/advisor/jobs/{job_a.id}/readiness", headers=auth_header(candidate_a)
    )
    completed = await client.post(
        f"/advisor/jobs/{job_a.id}/actions/{action_id}/status",
        json={"status": "completed"},
        headers=_headers(auth_header, candidate_a, "pr13-action-complete"),
    )
    assert completed.status_code == 200
    assert completed.json()["current_readiness_changed"] is False
    after = await client.get(
        f"/advisor/jobs/{job_a.id}/readiness", headers=auth_header(candidate_a)
    )
    assert before.json()["current"] == after.json()["current"]


async def _job_requiring_absent_skills(db_session, employer_a) -> JobDescription:
    """A target job whose required skills are absent from the candidate resume fixture."""
    job = JobDescription(
        employer_id=str(employer_a.id),
        title="平台工程师",
        raw_text="需要 Kubernetes 与 Terraform 的平台工程经验",
        parsed_json={
            "title": "平台工程师",
            "required_skills": ["Kubernetes", "Terraform"],
            "description": "平台工程师岗位描述",
            "location": "上海",
        },
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


def _capability_issue(payload: dict) -> dict:
    return next(
        item for item in payload["issues"] if item["issue_key"] == "capability:missing_skills"
    )


async def test_skill_absent_from_resume_never_routes_to_develop_without_user_confirmation(
    client, db_session, candidate_a, resume_a, employer_a, auth_header
):
    """R3-INV-01/INV-05: missing resume text is not evidence of missing capability."""
    job = await _job_requiring_absent_skills(db_session, employer_a)
    response = await client.post(
        f"/resumes/{resume_a.id}/jobs/{job.id}/diagnostics",
        headers=_headers(auth_header, candidate_a, "pr13-route-clarify"),
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    capability = _capability_issue(payload)
    assert capability["issue_type"] == "capability_gap"
    assert capability["claim_ids"] == []
    assert capability["route_state"] == "clarify"
    assert capability["route_reason"] == "missing_from_resume_needs_candidate_confirmation"
    assert [item for item in payload["issues"] if item["route_state"] == "develop"] == []


async def test_develop_state_requires_an_explicit_candidate_selected_plan(
    client, db_session, candidate_a, resume_a, employer_a, auth_header
):
    job = await _job_requiring_absent_skills(db_session, employer_a)
    payload = (
        await client.post(
            f"/resumes/{resume_a.id}/jobs/{job.id}/diagnostics",
            headers=_headers(auth_header, candidate_a, "pr13-route-develop"),
        )
    ).json()
    capability = _capability_issue(payload)
    strategy = next(item for item in capability["strategies"] if item["recommended"])

    selected = await client.post(
        f"/optimization/issues/{capability['id']}/select-strategy",
        json={"strategy_id": strategy["id"]},
        headers=_headers(auth_header, candidate_a, "pr13-route-select"),
    )
    assert selected.status_code == 200, selected.text

    refreshed = await client.get(
        f"/resumes/{resume_a.id}/jobs/{job.id}/diagnostics/{payload['diagnostic_id']}",
        headers=auth_header(candidate_a),
    )
    assert refreshed.status_code == 200, refreshed.text
    confirmed = _capability_issue(refreshed.json())
    assert confirmed["route_state"] == "develop"
    assert confirmed["route_reason"] == "candidate_selected_development_plan"


async def test_candidate_confirmed_development_survives_rediagnosis(
    client, db_session, candidate_a, resume_a, employer_a, auth_header
):
    job = await _job_requiring_absent_skills(db_session, employer_a)
    first = (
        await client.post(
            f"/resumes/{resume_a.id}/jobs/{job.id}/diagnostics",
            headers=_headers(auth_header, candidate_a, "pr13-route-survive-1"),
        )
    ).json()
    capability = _capability_issue(first)
    strategy = next(item for item in capability["strategies"] if item["recommended"])
    await client.post(
        f"/optimization/issues/{capability['id']}/select-strategy",
        json={"strategy_id": strategy["id"]},
        headers=_headers(auth_header, candidate_a, "pr13-route-survive-select"),
    )

    second = (
        await client.post(
            f"/resumes/{resume_a.id}/jobs/{job.id}/diagnostics",
            headers=_headers(auth_header, candidate_a, "pr13-route-survive-2"),
        )
    ).json()
    assert second["diagnostic_id"] != first["diagnostic_id"]
    assert _capability_issue(second)["route_state"] == "develop"


async def test_every_issue_carries_an_auditable_route_state(
    client, candidate_a, resume_a, job_a, auth_header
):
    payload = (
        await _diagnose(client, candidate_a, resume_a, job_a, auth_header, "pr13-route-invariants")
    ).json()
    assert payload["issues"]
    for issue in payload["issues"]:
        assert issue["route_state"] in {
            "ready",
            "clarify",
            "develop",
            "constraint",
            "unknown",
        }
        assert issue["route_reason"]
        if issue["route_state"] == "ready":
            assert issue["claim_ids"], "ready 状态必须有候选人来源"
        if issue["category"] == "hard_constraint":
            assert issue["route_state"] == "constraint"


async def test_diagnostic_idempotency_replays_same_result(
    client, candidate_a, resume_a, job_a, auth_header
):
    first = await _diagnose(client, candidate_a, resume_a, job_a, auth_header, "pr13-idempotent")
    second = await _diagnose(client, candidate_a, resume_a, job_a, auth_header, "pr13-idempotent")
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["diagnostic_id"] == second.json()["diagnostic_id"]
