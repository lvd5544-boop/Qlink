from __future__ import annotations

from copy import deepcopy

import pytest
from sqlalchemy import select

from app.models_db import ApplicationMessage, InterviewResult, Resume
from app import interview as interview_module


pytestmark = pytest.mark.asyncio


async def _pending_result(
    db_session,
    *,
    candidate,
    resume,
    application=None,
    mode="profile",
):
    extracted = (
        {
            "expected_job_title": "AI 平台工程师",
            "skills": ["Python", "FastAPI"],
            "summary": "候选人确认前不可见的面试摘要",
        }
        if mode == "profile"
        else {
            "answers": [
                {
                    "claim_id": "work_experience_0_action_0",
                    "claim_text": "负责订单模块优化",
                    "question": "提升了多少？",
                    "answer": "P95 延迟降低 35%",
                    "question_type": "metric",
                }
            ]
        }
    )
    row = InterviewResult(
        user_id=str(candidate.id),
        resume_id=str(resume.id),
        application_id=str(application.id) if application else None,
        mode=mode,
        status="pending_confirmation",
        transcript=[{"role": "user", "content": "private answer"}],
        extracted_json=extracted,
        source_references=[{"message_index": 0, "role": "user"}],
        allowed_uses={
            "resume_write": False,
            "job_recommendation": False,
            "employer_share": False,
            "model_improvement": False,
        },
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


async def test_pending_result_is_private_and_has_no_automatic_writeback(
    client,
    auth_header,
    db_session,
    candidate_a,
    candidate_b,
    resume_a,
    application_a,
):
    before = deepcopy(resume_a.parsed_json)
    row = await _pending_result(
        db_session,
        candidate=candidate_a,
        resume=resume_a,
        application=application_a,
    )

    owner = await client.get(
        f"/interviews/results/{row.id}",
        headers=auth_header(candidate_a),
    )
    assert owner.status_code == 200
    assert owner.json()["transcript"][0]["content"] == "private answer"

    denied = await client.get(
        f"/interviews/results/{row.id}",
        headers=auth_header(candidate_b),
    )
    assert denied.status_code == 404

    await db_session.refresh(resume_a)
    assert resume_a.parsed_json == before
    shared = (
        (
            await db_session.execute(
                select(ApplicationMessage).where(
                    ApplicationMessage.application_id == str(application_a.id),
                    ApplicationMessage.message_kind == "interview_summary",
                )
            )
        )
        .scalars()
        .all()
    )
    assert shared == []


async def test_each_confirmed_use_is_independent(
    client,
    auth_header,
    db_session,
    candidate_a,
    resume_a,
    application_a,
):
    row = await _pending_result(
        db_session,
        candidate=candidate_a,
        resume=resume_a,
        application=application_a,
    )
    response = await client.post(
        f"/interviews/results/{row.id}/confirm",
        headers=auth_header(candidate_a),
        json={
            "allowed_uses": {
                "resume_write": True,
                "job_recommendation": False,
                "employer_share": False,
                "model_improvement": False,
            },
            "resume_id": str(resume_a.id),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["allowed_uses"] == {
        "resume_write": True,
        "job_recommendation": False,
        "employer_share": False,
        "model_improvement": False,
    }
    await db_session.refresh(resume_a)
    assert resume_a.parsed_json["expected_job_title"] == "AI 平台工程师"
    assert resume_a.parsed_json["interview_provenance"][0]["interview_result_id"] == str(row.id)
    shared = (
        (
            await db_session.execute(
                select(ApplicationMessage).where(
                    ApplicationMessage.application_id == str(application_a.id),
                    ApplicationMessage.message_kind == "interview_summary",
                )
            )
        )
        .scalars()
        .all()
    )
    assert shared == []


async def test_explicit_employer_share_and_revoke_remove_derived_data(
    client,
    auth_header,
    db_session,
    candidate_a,
    resume_a,
    application_a,
):
    before = deepcopy(resume_a.parsed_json)
    row = await _pending_result(
        db_session,
        candidate=candidate_a,
        resume=resume_a,
        application=application_a,
        mode="claim_followup",
    )
    confirmed = await client.post(
        f"/interviews/results/{row.id}/confirm",
        headers=auth_header(candidate_a),
        json={
            "allowed_uses": {
                "resume_write": True,
                "job_recommendation": False,
                "employer_share": True,
                "model_improvement": False,
            },
            "resume_id": str(resume_a.id),
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    await db_session.refresh(resume_a)
    answers = resume_a.parsed_json["claim_followup_answers"]
    assert answers[0]["interview_result_id"] == str(row.id)

    messages = (
        (
            await db_session.execute(
                select(ApplicationMessage).where(
                    ApplicationMessage.application_id == str(application_a.id),
                    ApplicationMessage.message_kind == "interview_summary",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(messages) == 1
    assert messages[0].message_meta["candidate_confirmed"] is True

    resume_id = str(resume_a.id)
    result_id = str(row.id)
    application_id = str(application_a.id)
    revoked = await client.delete(
        f"/interviews/results/{result_id}",
        headers=auth_header(candidate_a),
    )
    assert revoked.status_code == 200
    db_session.expire_all()
    refreshed_resume = await db_session.get(Resume, resume_id)
    assert refreshed_resume.parsed_json == before
    refreshed_result = await db_session.get(InterviewResult, result_id)
    assert refreshed_result.status == "revoked"
    assert refreshed_result.transcript == []
    assert refreshed_result.extracted_json == {}
    remaining = (
        (
            await db_session.execute(
                select(ApplicationMessage).where(
                    ApplicationMessage.application_id == application_id,
                    ApplicationMessage.message_kind == "interview_summary",
                )
            )
        )
        .scalars()
        .all()
    )
    assert remaining == []


async def test_platform_provider_capacity_is_separate_from_user_fair_use(
    monkeypatch,
):
    monkeypatch.setattr(interview_module, "redis_client", None)
    interview_module._local_provider_calls.clear()
    monkeypatch.setenv("INTERVIEW_GLOBAL_PROVIDER_CALLS_PER_DAY", "1")

    await interview_module._reserve_provider_capacity()
    with pytest.raises(
        interview_module.ProviderCapacityExceeded,
        match="平台容量",
    ):
        await interview_module._reserve_provider_capacity()


async def test_production_capacity_guard_fails_closed_when_redis_fails(
    monkeypatch,
):
    class BrokenRedis:
        async def incr(self, _key):
            raise ConnectionError("redis unavailable")

    monkeypatch.setattr(interview_module, "redis_client", BrokenRedis())
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("INTERVIEW_GLOBAL_PROVIDER_CALLS_PER_DAY", "5000")

    with pytest.raises(
        interview_module.ProviderCapacityExceeded,
        match="容量保护",
    ):
        await interview_module._reserve_provider_capacity()
