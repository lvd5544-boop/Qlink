from __future__ import annotations

import asyncio
from copy import deepcopy
import uuid

import pytest
from sqlalchemy import select

from app.models_db import (
    CredibilityAuditRecord,
    JobApplication,
    JobRequirement,
    ScreeningResult,
    ScreeningRun,
)
from app.application_state import _content_hash

pytestmark = pytest.mark.asyncio


def _headers(auth_header, user, key: str | None = None):
    headers = auth_header(user)
    if key:
        headers["Idempotency-Key"] = key
    return headers


async def _prepare_confirmed_hard_requirement(
    client,
    db_session,
    *,
    employer,
    candidate,
    job,
    auth_header,
):
    profile = await client.get(
        f"/advisor/jobs/{job.id}/profile",
        headers=_headers(auth_header, candidate),
    )
    assert profile.status_code == 200, profile.text
    confirmed = await client.post(
        f"/advisor/jobs/{job.id}/profile/confirm",
        headers=_headers(auth_header, employer, f"confirm-{job.id}"),
    )
    assert confirmed.status_code == 200, confirmed.text
    rows = (
        (
            await db_session.execute(
                select(JobRequirement).where(
                    JobRequirement.profile_snapshot_id == confirmed.json()["snapshot"]["id"]
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows
    for row in rows:
        row.employer_confirmed = True
        if row.requirement_type in {"skill", "experience", "education", "location"}:
            row.is_hard_constraint = True
    await db_session.commit()
    hard = next(
        (row for row in rows if row.is_hard_constraint and row.requirement_type == "skill"),
        None,
    )
    if hard is None:
        hard = next(row for row in rows if row.is_hard_constraint)
    return confirmed.json(), hard


async def _create_configured_run(
    client,
    *,
    employer,
    job,
    hard,
    auth_header,
    key_prefix: str,
    extra_rules: list | None = None,
):
    created = await client.post(
        f"/employer/jobs/{job.id}/screening-runs",
        headers=_headers(auth_header, employer, f"{key_prefix}-create"),
    )
    assert created.status_code == 200, created.text
    run_id = created.json()["id"]
    rules = [
        {
            "rule_type": "hard_constraint",
            "field": "required_skill",
            "operator": "contains",
            "value": {"text": "Python"},
            "job_requirement_id": str(hard.id),
            "employer_confirmed": True,
            "legal_basis_note": "JD 已确认技能硬条件",
            "order_no": 0,
        },
        {
            "rule_type": "keyword",
            "field": "keyword",
            "operator": "contains",
            "value": {"text": "Python"},
            "order_no": 1,
        },
        {
            "rule_type": "taxonomy",
            "field": "canonical_skill",
            "operator": "contains",
            "value": {"text": "python"},
            "order_no": 2,
        },
    ]
    if extra_rules:
        rules.extend(extra_rules)
    configured = await client.post(
        f"/employer/screening-runs/{run_id}/rules",
        json={"rules": rules},
        headers=_headers(auth_header, employer, f"{key_prefix}-rules"),
    )
    assert configured.status_code == 200, configured.text
    return configured.json()


async def test_unauthorized_resume_excluded_and_employer_isolation(
    client,
    db_session,
    employer_a,
    employer_b,
    candidate_a,
    candidate_b,
    resume_b,
    job_a,
    application_a,
    auth_header,
):
    _, hard = await _prepare_confirmed_hard_requirement(
        client,
        db_session,
        employer=employer_a,
        candidate=candidate_a,
        job=job_a,
        auth_header=auth_header,
    )
    # Unauthorized application (employer invited) must not enter the run.
    rogue = JobApplication(
        id=str(uuid.uuid4()),
        job_id=str(job_a.id),
        employer_id=str(employer_a.id),
        candidate_id=str(candidate_b.id),
        resume_id=str(resume_b.id),
        status="submitted",
        pipeline_meta={"application_source": "employer_invited"},
    )
    db_session.add(rogue)
    await db_session.commit()

    run = await _create_configured_run(
        client,
        employer=employer_a,
        job=job_a,
        hard=hard,
        auth_header=auth_header,
        key_prefix="iso",
    )
    executed = await client.post(
        f"/employer/screening-runs/{run['id']}/execute",
        headers=_headers(auth_header, employer_a, "iso-exec"),
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["candidate_count"] == 1

    results = await client.get(
        f"/employer/screening-runs/{run['id']}/results",
        headers=_headers(auth_header, employer_a),
        params={"limit": 20, "offset": 0},
    )
    assert results.status_code == 200
    app_ids = {item["application_id"] for item in results.json()["items"]}
    assert str(application_a.id) in app_ids
    assert str(rogue.id) not in app_ids

    denied = await client.get(
        f"/employer/screening-runs/{run['id']}",
        headers=_headers(auth_header, employer_b),
    )
    assert denied.status_code == 404


async def test_illegal_hard_rule_and_sensitive_supplement(
    client,
    db_session,
    employer_a,
    candidate_a,
    job_a,
    auth_header,
):
    _, hard = await _prepare_confirmed_hard_requirement(
        client,
        db_session,
        employer=employer_a,
        candidate=candidate_a,
        job=job_a,
        auth_header=auth_header,
    )
    created = await client.post(
        f"/employer/jobs/{job_a.id}/screening-runs",
        headers=_headers(auth_header, employer_a, "bad-create"),
    )
    run_id = created.json()["id"]

    illegal_field = await client.post(
        f"/employer/screening-runs/{run_id}/rules",
        json={
            "rules": [
                {
                    "rule_type": "hard_constraint",
                    "field": "age",
                    "operator": "gte",
                    "value": {"text": "25"},
                    "job_requirement_id": str(hard.id),
                    "employer_confirmed": True,
                    "legal_basis_note": "非法年龄条件",
                }
            ]
        },
        headers=_headers(auth_header, employer_a, "bad-field"),
    )
    assert illegal_field.status_code == 422

    missing_note = await client.post(
        f"/employer/screening-runs/{run_id}/rules",
        json={
            "rules": [
                {
                    "rule_type": "hard_constraint",
                    "field": "required_skill",
                    "operator": "contains",
                    "value": {"text": "Python"},
                    "job_requirement_id": str(hard.id),
                    "employer_confirmed": True,
                    "legal_basis_note": "",
                }
            ]
        },
        headers=_headers(auth_header, employer_a, "bad-note"),
    )
    assert missing_note.status_code == 422

    sensitive = await client.post(
        f"/employer/screening-runs/{run_id}/rules",
        json={
            "rules": [
                {
                    "rule_type": "keyword",
                    "field": "keyword",
                    "operator": "contains",
                    "value": {"text": "候选人年龄要求"},
                }
            ]
        },
        headers=_headers(auth_header, employer_a, "bad-sensitive"),
    )
    assert sensitive.status_code == 422

    sensitive_english = await client.post(
        f"/employer/screening-runs/{run_id}/rules",
        json={
            "rules": [
                {
                    "rule_type": "keyword",
                    "field": "keyword",
                    "operator": "contains",
                    "value": {"text": "preferred age under 30"},
                }
            ]
        },
        headers=_headers(auth_header, employer_a, "bad-sensitive-en"),
    )
    assert sensitive_english.status_code == 422


async def test_unknown_is_not_fail_and_llm_cannot_mutate_status(
    client,
    db_session,
    employer_a,
    candidate_a,
    job_a,
    application_a,
    auth_header,
    monkeypatch,
):
    _, hard = await _prepare_confirmed_hard_requirement(
        client,
        db_session,
        employer=employer_a,
        candidate=candidate_a,
        job=job_a,
        auth_header=auth_header,
    )
    # Attach years_experience hard rule to an experience-typed requirement.
    exp = JobRequirement(
        id=str(uuid.uuid4()),
        profile_snapshot_id=str(hard.profile_snapshot_id),
        requirement_type="experience",
        raw_text="3 年相关经验",
        canonical_label="3 年相关经验",
        importance=90,
        requirement_level="required",
        is_hard_constraint=True,
        employer_confirmed=True,
    )
    db_session.add(exp)
    await db_session.commit()

    created = await client.post(
        f"/employer/jobs/{job_a.id}/screening-runs",
        headers=_headers(auth_header, employer_a, "unk-create"),
    )
    run_id = created.json()["id"]
    configured = await client.post(
        f"/employer/screening-runs/{run_id}/rules",
        json={
            "rules": [
                {
                    "rule_type": "hard_constraint",
                    "field": "years_experience",
                    "operator": "gte",
                    "value": {"text": "3"},
                    "job_requirement_id": str(exp.id),
                    "employer_confirmed": True,
                    "legal_basis_note": "年限硬条件",
                }
            ]
        },
        headers=_headers(auth_header, employer_a, "unk-rules"),
    )
    assert configured.status_code == 200, configured.text

    from app import screening as screening_mod

    async def _evil_llm(**kwargs):
        from app.screening import ScreeningLLMOutput

        return (
            ScreeningLLMOutput(
                evidence_summary=["evil"],
                alternative_explanations=["仍可能具备经验"],
                suggested_followups=["请补充年限"],
            ),
            {
                "model_called": True,
                "provider_status": "succeeded",
                "model_version": "test-model",
            },
        )

    monkeypatch.setattr(screening_mod, "run_screening_llm", _evil_llm)
    # Also try injecting hard_filter into parsed path via original function patched already.

    before_status = application_a.status
    executed = await client.post(
        f"/employer/screening-runs/{run_id}/execute",
        headers=_headers(auth_header, employer_a, "unk-exec"),
    )
    assert executed.status_code == 200, executed.text
    page = await client.get(
        f"/employer/screening-runs/{run_id}/results",
        headers=_headers(auth_header, employer_a),
    )
    item = page.json()["items"][0]
    assert item["hard_filter_status"] == "unknown"
    assert item["hard_filter_status"] != "fail"
    assert item["status"] == "pending_review"

    await db_session.refresh(application_a)
    assert application_a.status == before_status


async def test_snapshot_immutable_and_traceable(
    client,
    db_session,
    employer_a,
    candidate_a,
    job_a,
    resume_a,
    application_a,
    auth_header,
):
    profile, hard = await _prepare_confirmed_hard_requirement(
        client,
        db_session,
        employer=employer_a,
        candidate=candidate_a,
        job=job_a,
        auth_header=auth_header,
    )
    run = await _create_configured_run(
        client,
        employer=employer_a,
        job=job_a,
        hard=hard,
        auth_header=auth_header,
        key_prefix="snap",
    )
    # Explicitly select a newer application resume version before execution.
    # Screening must pin that version, not mix its ID with initial content.
    newer_resume = {
        "skills": [{"name": "Rust"}],
        "projects": [{"name": "Pinned v2 project"}],
    }
    meta = deepcopy(application_a.pipeline_meta or {})
    versions = list(meta.get("resume_versions") or [])
    versions.append(
        {
            "version_id": "v2",
            "resume_id": str(resume_a.id),
            "snapshot_json": newer_resume,
            "raw_text": "Pinned v2 project",
            "content_hash": _content_hash(newer_resume),
            "source": "candidate_replaced",
            "snapshot_status": "reliable",
        }
    )
    meta["resume_versions"] = versions
    meta["current_resume_version_id"] = "v2"
    application_a.pipeline_meta = meta
    await db_session.commit()

    executed = await client.post(
        f"/employer/screening-runs/{run['id']}/execute",
        headers=_headers(auth_header, employer_a, "snap-exec"),
    )
    assert executed.status_code == 200
    frozen_hash = executed.json()["profile_snapshot_hash"]

    job_a.parsed_json = {**(job_a.parsed_json or {}), "required_skills": ["Rust"]}
    resume_a.parsed_json = {**(resume_a.parsed_json or {}), "skills": [{"name": "Rust"}]}
    await db_session.commit()

    page = await client.get(
        f"/employer/screening-runs/{run['id']}/results",
        headers=_headers(auth_header, employer_a),
    )
    result_id = page.json()["items"][0]["id"]
    detail = await client.get(
        f"/employer/screening-results/{result_id}",
        headers=_headers(auth_header, employer_a),
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["requirement_refs"]
    assert body["resume_version_id"] == "v2"
    assert body["resume_content_hash"] == _content_hash(newer_resume)
    assert (
        detail.json()["decision_trace"]["observed_source_refs"][0]["profile_snapshot_hash"]
        == frozen_hash
    )
    rerun = await client.get(
        f"/employer/screening-runs/{run['id']}",
        headers=_headers(auth_header, employer_a),
    )
    assert rerun.json()["profile_snapshot_hash"] == frozen_hash
    assert rerun.json()["profile_snapshot_hash"] == profile["snapshot"]["snapshot_hash"]


async def test_hard_rule_value_is_server_derived_and_rules_are_immutable(
    client,
    db_session,
    employer_a,
    candidate_a,
    job_a,
    auth_header,
):
    _, hard = await _prepare_confirmed_hard_requirement(
        client,
        db_session,
        employer=employer_a,
        candidate=candidate_a,
        job=job_a,
        auth_header=auth_header,
    )
    created = await client.post(
        f"/employer/jobs/{job_a.id}/screening-runs",
        headers=_headers(auth_header, employer_a, "derived-create"),
    )
    run_id = created.json()["id"]
    body = {
        "rules": [
            {
                "rule_type": "hard_constraint",
                "field": "required_skill",
                "operator": "contains",
                "value": {"text": "客户端虚构的更严格条件"},
                "job_requirement_id": str(hard.id),
                "employer_confirmed": True,
                "legal_basis_note": "JD 已确认技能硬条件",
            }
        ]
    }
    configured = await client.post(
        f"/employer/screening-runs/{run_id}/rules",
        json=body,
        headers=_headers(auth_header, employer_a, "derived-rules"),
    )
    assert configured.status_code == 200, configured.text
    stored_value = configured.json()["rules"][0]["value"]["text"]
    assert stored_value != "客户端虚构的更严格条件"
    assert stored_value in {hard.canonical_label, hard.raw_text}

    duplicate = await client.post(
        f"/employer/screening-runs/{run_id}/rules",
        json=body,
        headers=_headers(auth_header, employer_a, "derived-rules-other-key"),
    )
    assert duplicate.status_code == 409


async def test_provider_failure_still_pending_review(
    client,
    db_session,
    employer_a,
    candidate_a,
    job_a,
    application_a,
    auth_header,
    monkeypatch,
):
    _, hard = await _prepare_confirmed_hard_requirement(
        client,
        db_session,
        employer=employer_a,
        candidate=candidate_a,
        job=job_a,
        auth_header=auth_header,
    )
    run = await _create_configured_run(
        client,
        employer=employer_a,
        job=job_a,
        hard=hard,
        auth_header=auth_header,
        key_prefix="pf",
    )

    from app import screening as screening_mod

    async def _failing_llm(**kwargs):
        from app.screening import ScreeningLLMOutput

        return (
            ScreeningLLMOutput(
                evidence_summary=["规则层摘要"],
                alternative_explanations=["可能是表述差异"],
                suggested_followups=["请补充证据"],
            ),
            {
                "model_called": True,
                "provider_status": "failed",
                "failure_category": "ProviderTimeout",
            },
        )

    monkeypatch.setattr(screening_mod, "run_screening_llm", _failing_llm)
    executed = await client.post(
        f"/employer/screening-runs/{run['id']}/execute",
        headers=_headers(auth_header, employer_a, "pf-exec"),
    )
    assert executed.status_code == 200
    page = await client.get(
        f"/employer/screening-runs/{run['id']}/results",
        headers=_headers(auth_header, employer_a),
    )
    item = page.json()["items"][0]
    assert item["status"] == "pending_review"
    detail = await client.get(
        f"/employer/screening-results/{item['id']}",
        headers=_headers(auth_header, employer_a),
    )
    uncertainties = detail.json()["decision_trace"]["uncertainties"]
    assert any(
        isinstance(item, dict) and item.get("category") == "provider_failure"
        for item in uncertainties
    )


async def test_taxonomy_does_not_add_requirements(
    client,
    db_session,
    employer_a,
    candidate_a,
    job_a,
    application_a,
    auth_header,
):
    _, hard = await _prepare_confirmed_hard_requirement(
        client,
        db_session,
        employer=employer_a,
        candidate=candidate_a,
        job=job_a,
        auth_header=auth_header,
    )
    run = await _create_configured_run(
        client,
        employer=employer_a,
        job=job_a,
        hard=hard,
        auth_header=auth_header,
        key_prefix="tax",
    )
    await client.post(
        f"/employer/screening-runs/{run['id']}/execute",
        headers=_headers(auth_header, employer_a, "tax-exec"),
    )
    page = await client.get(
        f"/employer/screening-runs/{run['id']}/results",
        headers=_headers(auth_header, employer_a),
    )
    hits = page.json()["items"][0]["keyword_hits"]
    assert hits
    assert all(hit.get("adds_requirement") is False for hit in hits)


async def test_idempotent_execute_and_unique_result(
    client,
    db_session,
    employer_a,
    candidate_a,
    job_a,
    application_a,
    auth_header,
):
    _, hard = await _prepare_confirmed_hard_requirement(
        client,
        db_session,
        employer=employer_a,
        candidate=candidate_a,
        job=job_a,
        auth_header=auth_header,
    )
    run = await _create_configured_run(
        client,
        employer=employer_a,
        job=job_a,
        hard=hard,
        auth_header=auth_header,
        key_prefix="idem",
    )
    first = await client.post(
        f"/employer/screening-runs/{run['id']}/execute",
        headers=_headers(auth_header, employer_a, "idem-exec-same"),
    )
    second = await client.post(
        f"/employer/screening-runs/{run['id']}/execute",
        headers=_headers(auth_header, employer_a, "idem-exec-same"),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    third = await client.post(
        f"/employer/screening-runs/{run['id']}/execute",
        headers=_headers(auth_header, employer_a, "idem-exec-other"),
    )
    assert third.status_code == 200
    rows = (
        (
            await db_session.execute(
                select(ScreeningResult).where(ScreeningResult.run_id == run["id"])
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_mark_reviewed_and_clarification_reuse(
    client,
    db_session,
    employer_a,
    candidate_a,
    job_a,
    application_a,
    auth_header,
):
    _, hard = await _prepare_confirmed_hard_requirement(
        client,
        db_session,
        employer=employer_a,
        candidate=candidate_a,
        job=job_a,
        auth_header=auth_header,
    )
    run = await _create_configured_run(
        client,
        employer=employer_a,
        job=job_a,
        hard=hard,
        auth_header=auth_header,
        key_prefix="rev",
    )
    await client.post(
        f"/employer/screening-runs/{run['id']}/execute",
        headers=_headers(auth_header, employer_a, "rev-exec"),
    )
    page = await client.get(
        f"/employer/screening-runs/{run['id']}/results",
        headers=_headers(auth_header, employer_a),
    )
    result_id = page.json()["items"][0]["id"]
    reviewed = await client.post(
        f"/employer/screening-results/{result_id}/mark-reviewed",
        headers=_headers(auth_header, employer_a, "rev-mark"),
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "reviewed"
    assert "造假" not in reviewed.text

    clarified = await client.post(
        f"/employer/screening-results/{result_id}/clarification",
        json={
            "claim_text": "负责订单模块开发与性能优化",
            "questions": ["请补充性能指标口径？"],
        },
        headers=_headers(auth_header, employer_a, "rev-clarify"),
    )
    assert clarified.status_code == 200, clarified.text
    assert clarified.json()["result"]["status"] == "clarification_requested"
    assert "造假" not in clarified.text


async def test_result_filters_candidate_name_and_bulk_review(
    client,
    db_session,
    employer_a,
    candidate_a,
    job_a,
    application_a,
    auth_header,
):
    _, hard = await _prepare_confirmed_hard_requirement(
        client,
        db_session,
        employer=employer_a,
        candidate=candidate_a,
        job=job_a,
        auth_header=auth_header,
    )
    run = await _create_configured_run(
        client,
        employer=employer_a,
        job=job_a,
        hard=hard,
        auth_header=auth_header,
        key_prefix="bulk-review",
    )
    executed = await client.post(
        f"/employer/screening-runs/{run['id']}/execute",
        headers=_headers(auth_header, employer_a, "bulk-review-exec"),
    )
    assert executed.status_code == 200, executed.text

    pending = await client.get(
        f"/employer/screening-runs/{run['id']}/results",
        params={"review_status": "pending_review"},
        headers=_headers(auth_header, employer_a),
    )
    assert pending.status_code == 200
    assert pending.json()["total"] == 1
    result = pending.json()["items"][0]
    assert result["candidate_name"] == "Candidate A"

    reviewed = await client.post(
        f"/employer/screening-runs/{run['id']}/results/mark-reviewed",
        json={"result_ids": [result["id"]]},
        headers=_headers(auth_header, employer_a, "bulk-review-mark"),
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["updated"] == 1

    remaining = await client.get(
        f"/employer/screening-runs/{run['id']}/results",
        params={"review_status": "pending_review"},
        headers=_headers(auth_header, employer_a),
    )
    assert remaining.json()["total"] == 0
    completed = await client.get(
        f"/employer/screening-runs/{run['id']}/results",
        params={"review_status": "reviewed"},
        headers=_headers(auth_header, employer_a),
    )
    assert completed.json()["total"] == 1


async def test_new_credibility_audit_omits_risk_score(
    client,
    db_session,
    employer_a,
    application_a,
    auth_header,
):
    response = await client.get(
        f"/applications/{application_a.id}/credibility-audit",
        headers=_headers(auth_header, employer_a, "cred-new"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "risk_score" not in body
    assert "risk_score" not in (body.get("report") or {})

    record = (
        (
            await db_session.execute(
                select(CredibilityAuditRecord)
                .where(CredibilityAuditRecord.application_id == str(application_a.id))
                .order_by(CredibilityAuditRecord.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert record is not None
    assert record.risk_score is None


async def test_concurrent_execute_unique_constraint(
    client,
    db_session,
    employer_a,
    candidate_a,
    job_a,
    application_a,
    auth_header,
):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row locks / concurrent writers")
    _, hard = await _prepare_confirmed_hard_requirement(
        client,
        db_session,
        employer=employer_a,
        candidate=candidate_a,
        job=job_a,
        auth_header=auth_header,
    )
    run = await _create_configured_run(
        client,
        employer=employer_a,
        job=job_a,
        hard=hard,
        auth_header=auth_header,
        key_prefix="conc",
    )

    async def _exec(key: str):
        return await client.post(
            f"/employer/screening-runs/{run['id']}/execute",
            headers=_headers(auth_header, employer_a, key),
        )

    first, second = await asyncio.gather(
        _exec("conc-a"),
        _exec("conc-b"),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    rows = (
        (
            await db_session.execute(
                select(ScreeningResult).where(ScreeningResult.run_id == run["id"])
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    runs = (
        (await db_session.execute(select(ScreeningRun).where(ScreeningRun.id == run["id"])))
        .scalars()
        .all()
    )
    assert runs[0].status == "completed"
