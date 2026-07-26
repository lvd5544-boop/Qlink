"""PR1：审计与反馈跨租户权限封堵。"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models_db import AuditFindingFeedback, MatchResult


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _disable_llm(monkeypatch):
    """审计正向路径不打真实模型。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")


async def _feedback_count(test_engine) -> int:
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(select(func.count()).select_from(AuditFindingFeedback))
        return int(result.scalar() or 0)


async def test_employer_a_can_audit_own_application_resume(
    client, auth_header, employer_a, job_a, resume_a, application_a
):
    res = await client.get(
        f"/applications/job/{job_a.id}/resume/{resume_a.id}/credibility-audit",
        headers=auth_header(employer_a),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["job_id"] == str(job_a.id)
    assert body["resume_id"] == str(resume_a.id)
    assert body["application_id"] == str(application_a.id)
    assert body.get("audit_record_id")
    assert "report" in body


async def test_employer_a_cannot_audit_unrelated_resume_on_own_job(
    client, auth_header, employer_a, job_a, resume_b
):
    res = await client.get(
        f"/applications/job/{job_a.id}/resume/{resume_b.id}/credibility-audit",
        headers=auth_header(employer_a),
    )
    assert res.status_code == 404


async def test_employer_a_cannot_audit_employer_b_application_resume(
    client, auth_header, employer_a, job_b, resume_b, application_b
):
    res = await client.get(
        f"/applications/job/{job_b.id}/resume/{resume_b.id}/credibility-audit",
        headers=auth_header(employer_a),
    )
    assert res.status_code == 404


async def test_match_only_without_application_cannot_audit(
    client,
    auth_header,
    db_session,
    employer_a,
    job_a,
    resume_b,
):
    match = MatchResult(
        resume_id=str(resume_b.id),
        job_id=str(job_a.id),
        score=8.0,
        reason="match-only fixture",
    )
    db_session.add(match)
    await db_session.commit()

    res = await client.get(
        f"/applications/job/{job_a.id}/resume/{resume_b.id}/credibility-audit",
        headers=auth_header(employer_a),
    )
    assert res.status_code == 404


async def test_employer_a_cannot_feedback_on_employer_b_audit(
    client, auth_header, test_engine, employer_a, audit_record_b, application_b
):
    before = await _feedback_count(test_engine)
    res = await client.post(
        "/applications/feedback/audit-finding",
        headers=auth_header(employer_a),
        json={
            "audit_record_id": str(audit_record_b.id),
            "application_id": str(application_b.id),
            "finding_id": "finding_x",
            "claim_id": "claim_x",
            "label": "useful",
            "note": "cross-tenant should fail",
        },
    )
    assert res.status_code == 404
    assert await _feedback_count(test_engine) == before


async def test_employer_a_legitimate_feedback_succeeds(
    client, auth_header, test_engine, employer_a, audit_record_a, application_a
):
    before = await _feedback_count(test_engine)
    res = await client.post(
        "/applications/feedback/audit-finding",
        headers=auth_header(employer_a),
        json={
            "audit_record_id": str(audit_record_a.id),
            "application_id": str(application_a.id),
            "finding_id": "finding_a_1",
            "claim_id": "work_experience_0_action_0",
            "label": "useful",
            "note": "ok",
            "finding_snapshot": {
                "id": "finding_a_1",
                "claim_id": "work_experience_0_action_0",
                "severity": "medium",
                "title": "缺少可验证指标",
            },
        },
    )
    assert res.status_code == 200
    assert res.json().get("feedback_id")
    assert await _feedback_count(test_engine) == before + 1


async def test_mixed_audit_a_with_application_b_fails(
    client, auth_header, test_engine, employer_a, audit_record_a, application_b
):
    before = await _feedback_count(test_engine)
    res = await client.post(
        "/applications/feedback/audit-finding",
        headers=auth_header(employer_a),
        json={
            "audit_record_id": str(audit_record_a.id),
            "application_id": str(application_b.id),
            "label": "false_positive",
        },
    )
    assert res.status_code == 404
    assert await _feedback_count(test_engine) == before


async def test_client_cannot_override_feedback_employer_id(
    client, auth_header, test_engine, employer_a, employer_b, audit_record_a, application_a
):
    """即使 JSON 夹带 employer_id，也必须以当前登录雇主落库。"""
    res = await client.post(
        "/applications/feedback/audit-finding",
        headers=auth_header(employer_a),
        json={
            "audit_record_id": str(audit_record_a.id),
            "application_id": str(application_a.id),
            "label": "unclear",
            "employer_id": str(employer_b.id),
        },
    )
    assert res.status_code == 200
    fb_id = res.json()["feedback_id"]
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        fb = await session.get(AuditFindingFeedback, fb_id)
        assert fb is not None
        assert fb.employer_id == str(employer_a.id)
        assert fb.employer_id != str(employer_b.id)
