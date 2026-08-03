from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models_db import (
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
        await db_session.execute(
            select(OptimizationIssue).where(
                OptimizationIssue.diagnostic_id == payload["diagnostic_id"]
            )
        )
    ).scalars().all()
    assert len(rows) == len(payload["issues"])


async def test_rewrite_uses_candidate_claims_not_jd_and_requires_confirmation(
    client, candidate_a, resume_a, job_a, auth_header
):
    diagnostic = (await _diagnose(
        client, candidate_a, resume_a, job_a, auth_header, "pr13-rewrite-diag"
    )).json()
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
    diagnostic = (await _diagnose(
        client, candidate_a, resume_a, job_a, auth_header, "pr13-tamper-diag"
    )).json()
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
    diagnostic = (await _diagnose(
        client, candidate_a, resume_a, job_a, auth_header, "pr13-apply-diag"
    )).json()
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
        await db_session.execute(
            select(ResumeVersion)
            .where(ResumeVersion.resume_id == str(resume_a.id))
            .order_by(ResumeVersion.version_number)
        )
    ).scalars().all()
    assert len(versions) == 2
    assert versions[0].id == diagnostic["resume_version_id"]
    assert versions[0].parsed_json_snapshot["summary"] == proposal["before_text"]
    assert versions[1].parsed_json_snapshot["summary"] == proposal["after_text"]


async def test_completed_future_action_does_not_raise_current_readiness(
    client, candidate_a, resume_a, job_a, auth_header
):
    diagnostic = (await _diagnose(
        client, candidate_a, resume_a, job_a, auth_header, "pr13-action-diag"
    )).json()
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


async def test_diagnostic_idempotency_replays_same_result(
    client, candidate_a, resume_a, job_a, auth_header
):
    first = await _diagnose(
        client, candidate_a, resume_a, job_a, auth_header, "pr13-idempotent"
    )
    second = await _diagnose(
        client, candidate_a, resume_a, job_a, auth_header, "pr13-idempotent"
    )
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["diagnostic_id"] == second.json()["diagnostic_id"]
