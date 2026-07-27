"""PR8 Claim Passport ownership, provenance and immutable snapshot regression tests."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models_db import ClaimEvent, ResumeSuggestion
from app.models import ResumeInfo
from app.resume_suggestion_store import sync_suggestions_for_source

pytestmark = pytest.mark.asyncio


async def _apply(client, auth_header, candidate, resume, job):
    response = await client.post(
        "/applications",
        headers=auth_header(candidate),
        json={"resume_id": str(resume.id), "job_id": str(job.id)},
    )
    assert response.status_code == 200, response.text
    return response.json()["application"]


async def test_claim_sync_evidence_withdrawal_preserves_event_but_redacts_content(
    client, auth_header, candidate_a, resume_a, db_session
):
    synced = await client.post(
        f"/resumes/{resume_a.id}/claims/sync", headers=auth_header(candidate_a)
    )
    assert synced.status_code == 200, synced.text
    claim = next(item for item in synced.json()["claims"] if item["section"] == "work_experience")

    created = await client.post(
        f"/resumes/{resume_a.id}/claims/{claim['id']}/evidence",
        headers=auth_header(candidate_a),
        json={"evidence_type": "metric_context", "summary": "峰值流量口径来自内部监控报表"},
    )
    assert created.status_code == 200, created.text
    evidence_id = created.json()["evidence_id"]

    visible = await client.get(f"/resumes/{resume_a.id}/claims", headers=auth_header(candidate_a))
    item = next(row for row in visible.json()["claims"] if row["id"] == claim["id"])
    assert item["evidence_state"] == "supported_by_user_evidence"
    assert item["workflow_state"] == "answered"

    withdrawn = await client.delete(
        f"/resumes/{resume_a.id}/claims/evidence/{evidence_id}",
        headers=auth_header(candidate_a),
    )
    assert withdrawn.status_code == 200, withdrawn.text
    visible = await client.get(f"/resumes/{resume_a.id}/claims", headers=auth_header(candidate_a))
    item = next(row for row in visible.json()["claims"] if row["id"] == claim["id"])
    assert item["evidence"][0]["summary"] is None
    assert item["evidence"][0]["verification_status"] == "withdrawn"
    events = await db_session.execute(select(ClaimEvent).where(ClaimEvent.claim_id == claim["id"]))
    assert any(event.event_type == "evidence_withdrawn" for event in events.scalars())


async def test_passport_application_snapshot_is_immutable_and_cross_tenant_hidden(
    client, auth_header, candidate_a, employer_a, employer_b, resume_a, job_a, db_session
):
    application = await _apply(client, auth_header, candidate_a, resume_a, job_a)
    passport = await client.get(
        f"/applications/{application['id']}/claim-passport", headers=auth_header(employer_a)
    )
    assert passport.status_code == 200, passport.text
    assert passport.json()["claims"]
    before = passport.json()["claims"][0]["text_snapshot"]
    claim_id = passport.json()["claims"][0]["claim_id"]

    later_evidence = await client.post(
        f"/resumes/{resume_a.id}/claims/{claim_id}/evidence",
        headers=auth_header(candidate_a),
        json={"summary": "仅候选人与平台可见的投递后补充说明"},
    )
    assert later_evidence.status_code == 200, later_evidence.text

    resume_a.parsed_json["work_experience"][0]["description"] = "后续修改，不得污染历史申请快照"
    await db_session.commit()
    await client.post(f"/resumes/{resume_a.id}/claims/sync", headers=auth_header(candidate_a))
    again = await client.get(
        f"/applications/{application['id']}/claim-passport", headers=auth_header(employer_a)
    )
    assert again.status_code == 200
    assert again.json()["claims"][0]["text_snapshot"] == before
    assert "仅候选人与平台可见" not in str(again.json())

    denied = await client.get(
        f"/applications/{application['id']}/claim-passport", headers=auth_header(employer_b)
    )
    assert denied.status_code == 404


async def test_candidate_cannot_add_evidence_to_another_candidates_claim(
    client, auth_header, candidate_a, candidate_b, resume_a
):
    sync = await client.post(
        f"/resumes/{resume_a.id}/claims/sync", headers=auth_header(candidate_a)
    )
    claim_id = sync.json()["claims"][0]["id"]
    denied = await client.post(
        f"/resumes/{resume_a.id}/claims/{claim_id}/evidence",
        headers=auth_header(candidate_b),
        json={"summary": "越权写入"},
    )
    assert denied.status_code == 404


async def test_authorized_employer_can_record_conflict_without_fact_verdict(
    client, auth_header, candidate_a, employer_a, employer_b, resume_a, job_a
):
    application = await _apply(client, auth_header, candidate_a, resume_a, job_a)
    candidate_claims = await client.get(
        f"/resumes/{resume_a.id}/claims", headers=auth_header(candidate_a)
    )
    source_key = candidate_claims.json()["claims"][0]["source_key"]

    denied = await client.post(
        f"/applications/{application['id']}/claim-conflicts",
        headers=auth_header(employer_b),
        json={"claim_id": source_key, "reason": "需要澄清两个来源的时间范围"},
    )
    assert denied.status_code == 404

    recorded = await client.post(
        f"/applications/{application['id']}/claim-conflicts",
        headers=auth_header(employer_a),
        json={"claim_id": source_key, "reason": "需要澄清两个来源的时间范围"},
    )
    assert recorded.status_code == 200, recorded.text
    assert "不代表对事实作出判定" in recorded.json()["message"]

    refreshed = await client.get(f"/resumes/{resume_a.id}/claims", headers=auth_header(candidate_a))
    claim = next(item for item in refreshed.json()["claims"] if item["source_key"] == source_key)
    assert claim["evidence_state"] == "conflict_detected"
    assert claim["workflow_state"] == "reviewed"
    assert any(item["event_type"] == "conflict_detected" for item in claim["events"])


async def test_claim_uuid_survives_same_source_key_text_update(
    client, auth_header, candidate_a, resume_a, db_session
):
    first = await client.post(
        f"/resumes/{resume_a.id}/claims/sync", headers=auth_header(candidate_a)
    )
    action = next(item for item in first.json()["claims"] if item["section"] == "work_experience")
    resume_a.parsed_json["work_experience"][0]["description"] = (
        "负责订单模块开发、性能优化与监控告警"
    )
    await db_session.commit()
    second = await client.post(
        f"/resumes/{resume_a.id}/claims/sync", headers=auth_header(candidate_a)
    )
    same_key = next(
        item for item in second.json()["claims"] if item["source_key"] == action["source_key"]
    )
    assert same_key["id"] == action["id"]
    assert same_key["original_text"] == action["original_text"]


async def test_parse_resume_creates_passport_claims_immediately(
    client, auth_header, candidate_a, monkeypatch, tmp_path
):
    monkeypatch.setattr("app.main.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.main.parse_with_llm",
        lambda text: ResumeInfo(
            name="Passport Candidate",
            summary=text,
            work_experience=[
                {
                    "company": "Example",
                    "position": "Engineer",
                    "duration_years": 1,
                    "description": "负责平台接口开发",
                }
            ],
        ),
    )
    parsed = await client.post(
        "/parse-resume",
        headers=auth_header(candidate_a),
        files={"file": ("resume.txt", b"resume content", "text/plain")},
    )
    assert parsed.status_code == 200, parsed.text
    resume_id = parsed.json()["resume_id"]
    claims = await client.get(f"/resumes/{resume_id}/claims", headers=auth_header(candidate_a))
    assert claims.status_code == 200
    assert claims.json()["claims"]


async def test_evidence_followup_persists_candidate_answers_as_passport_evidence(
    client, auth_header, candidate_a, resume_a
):
    generated = await client.post(
        f"/resumes/{resume_a.id}/evidence-followup/regenerate",
        headers={**auth_header(candidate_a), "Idempotency-Key": "pr8-evidence-passport-1"},
        json={
            "entry_type": "work",
            "index": 0,
            "answers": [{"id": "result", "answer": "P99 从 200ms 降至 120ms"}],
            "rewrite_mode": "conservative",
        },
    )
    assert generated.status_code == 200, generated.text
    claims = await client.get(f"/resumes/{resume_a.id}/claims", headers=auth_header(candidate_a))
    assert any(
        evidence["source"] == "evidence_followup"
        for claim in claims.json()["claims"]
        for evidence in claim["evidence"]
    )


async def test_faithful_suggestion_apply_records_passport_revision(
    client, auth_header, candidate_a, resume_a, db_session
):
    original = resume_a.parsed_json["work_experience"][0]["description"]
    await sync_suggestions_for_source(
        db_session,
        str(resume_a.id),
        "health_check",
        [
            {
                "id": "pr8-revision-proof",
                "source": "health_check",
                "title": "补充已有量化结果",
                "requires_evidence": True,
                "needs_followup": True,
                "original_text": original,
                "patch": {
                    "action": "append_quantification",
                    "section": "work_experience",
                    "index": 0,
                    "value": None,
                    "requires_evidence": True,
                },
            }
        ],
    )
    suggestion = (
        (
            await db_session.execute(
                select(ResumeSuggestion).where(
                    ResumeSuggestion.resume_id == str(resume_a.id),
                    ResumeSuggestion.suggestion_key == "pr8-revision-proof",
                )
            )
        )
        .scalars()
        .one()
    )
    generated = await client.post(
        f"/resumes/{resume_a.id}/evidence-followup/regenerate",
        headers={**auth_header(candidate_a), "Idempotency-Key": "pr8-revision-evidence-1"},
        json={
            "entry_type": "work",
            "index": 0,
            "answers": [{"id": "result", "answer": "P99 从 200ms 降至 120ms"}],
            "rewrite_mode": "conservative",
        },
    )
    assert generated.status_code == 200, generated.text
    output = generated.json()
    applied = await client.post(
        f"/resumes/{resume_a.id}/apply-suggestion",
        headers=auth_header(candidate_a),
        json={
            "suggestion_id": str(suggestion.id),
            "patch": {
                "action": "append_quantification",
                "section": "work_experience",
                "index": 0,
                "value": output["example_after"],
                "evidence_completed": True,
                "evidence_references": output["evidence_references"],
                "fidelity_result": output["fidelity_result"],
                "fidelity_proof": output["fidelity_proof"],
            },
        },
    )
    assert applied.status_code == 200, applied.text
    claims = await client.get(f"/resumes/{resume_a.id}/claims", headers=auth_header(candidate_a))
    revisions = [revision for claim in claims.json()["claims"] for revision in claim["revisions"]]
    assert any(
        revision["rewrite_mode"] == "suggestion_apply"
        and revision["before_text"] != revision["after_text"]
        and revision["fidelity_result"]
        for revision in revisions
    ), revisions
