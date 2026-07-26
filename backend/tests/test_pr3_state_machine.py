"""
PR3 回归测试：状态机与申请简历不可变。

覆盖：
- 通用 status PATCH 不得直设 needs_clarification / clarified / interview_invited；
- 招聘方通用 PATCH 只能 viewed / rejected / accepted；
- 招聘方「人工关闭澄清」显式动作关闭开放 Claim 并留痕；
- 重复申请、澄清、邀请不改变原 resume_id；
- 候选人显式换简历需确认并留痕。
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_db import (
    ApplicationMessage,
    InterviewInvitation,
    JobApplication,
    Resume,
)

pytestmark = pytest.mark.asyncio


async def test_generic_patch_rejects_business_only_statuses(
    client, auth_header, employer_a, application_a
):
    for status in (
        "needs_clarification",
        "clarified",
        "clarification_closed",
        "interview_invited",
    ):
        res = await client.patch(
            f"/applications/{application_a.id}/status",
            headers=auth_header(employer_a),
            json={"status": status},
        )
        assert res.status_code == 403, f"{status} 应被拒绝，实际 {res.status_code}"


@pytest.mark.parametrize("status", ["accepted", "rejected"])
async def test_employer_can_patch_terminal_status_from_nonterminal(
    status, client, auth_header, employer_a, application_a
):
    res = await client.patch(
        f"/applications/{application_a.id}/status",
        headers=auth_header(employer_a),
        json={"status": status},
    )
    assert res.status_code == 200, res.text
    assert res.json()["application"]["status"] == status


async def test_candidate_cannot_patch_any_status(client, auth_header, candidate_a, application_a):
    for status in ("viewed", "clarified", "accepted", "rejected"):
        res = await client.patch(
            f"/applications/{application_a.id}/status",
            headers=auth_header(candidate_a),
            json={"status": status},
        )
        assert res.status_code == 403, f"{status}: {res.status_code}"


@pytest.mark.parametrize(
    ("terminal", "target"),
    [
        ("accepted", "rejected"),
        ("accepted", "viewed"),
        ("rejected", "accepted"),
        ("rejected", "viewed"),
    ],
)
async def test_terminal_status_cannot_be_reopened_by_generic_patch(
    terminal, target, client, auth_header, employer_a, application_a, db_session
):
    first = await client.patch(
        f"/applications/{application_a.id}/status",
        headers=auth_header(employer_a),
        json={"status": terminal},
    )
    assert first.status_code == 200, first.text

    await db_session.refresh(application_a)
    history_before = list((application_a.pipeline_meta or {}).get("status_history", []))
    reopened = await client.patch(
        f"/applications/{application_a.id}/status",
        headers=auth_header(employer_a),
        json={"status": target},
    )
    assert reopened.status_code == 409, reopened.text
    await db_session.refresh(application_a)
    assert application_a.status == terminal
    assert (application_a.pipeline_meta or {}).get("status_history", []) == history_before


async def test_employer_manual_close_clarification(
    client, auth_header, employer_a, application_a, db_session
):
    # application_a 初始有两个开放 Claim，状态 needs_clarification
    res = await client.post(
        f"/applications/{application_a.id}/clarification/close",
        headers=auth_header(employer_a),
        json={"reason": "长期未回复，人工关闭"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["closed_claim_count"] == 2
    assert body["application"]["status"] == "clarification_closed"
    assert body["open_claim_count"] == 0

    # 校验留痕：线程 closed + 关闭人 + 原因
    threads = body["claim_threads"]
    assert threads, "应存在 claim 线程"
    for t in threads:
        assert t.get("status") == "closed"
        assert t.get("closed_by") == str(employer_a.id)
        assert t.get("close_reason")
        assert t.get("closed_at")
        assert t.get("response_message_id") is None
        assert t.get("answered_at") is None


@pytest.mark.parametrize("reason", [None, "", "   "])
async def test_manual_close_requires_nonblank_reason(
    reason, client, auth_header, employer_a, application_a, db_session
):
    before = dict(application_a.pipeline_meta or {})
    res = await client.post(
        f"/applications/{application_a.id}/clarification/close",
        headers=auth_header(employer_a),
        json={"reason": reason},
    )
    assert res.status_code == 422
    await db_session.refresh(application_a)
    assert application_a.status == "needs_clarification"
    assert application_a.pipeline_meta == before


async def test_manual_close_without_open_claims_returns_400(
    client, auth_header, employer_a, application_a
):
    first = await client.post(
        f"/applications/{application_a.id}/clarification/close",
        headers=auth_header(employer_a),
        json={"reason": "关闭"},
    )
    assert first.status_code == 200
    second = await client.post(
        f"/applications/{application_a.id}/clarification/close",
        headers=auth_header(employer_a),
        json={"reason": "再次关闭"},
    )
    assert second.status_code == 400


async def test_manual_close_forbidden_for_candidate(
    client, auth_header, candidate_a, application_a
):
    res = await client.post(
        f"/applications/{application_a.id}/clarification/close",
        headers=auth_header(candidate_a),
        json={"reason": "候选人不应能关闭"},
    )
    assert res.status_code == 403


async def test_duplicate_apply_does_not_change_resume_id(
    client, auth_header, candidate_a, resume_a, job_a, db_session
):
    # 第二份简历
    other = Resume(
        user_id=str(candidate_a.id),
        raw_text="Candidate A resume v2",
        parsed_json={"name": "Candidate A", "expected_job_title": "后端工程师"},
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    first = await client.post(
        "/applications",
        headers=auth_header(candidate_a),
        json={"job_id": str(job_a.id), "resume_id": str(resume_a.id)},
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "ok"

    dup = await client.post(
        "/applications",
        headers=auth_header(candidate_a),
        json={"job_id": str(job_a.id), "resume_id": str(other.id)},
    )
    assert dup.status_code == 200, dup.text
    payload = dup.json()
    assert payload["status"] == "exists"
    # resume_id 未被静默替换
    assert payload["application"]["resume_id"] == str(resume_a.id)
    assert payload.get("resume_change_required_explicit") is True


async def test_explicit_resume_change_requires_confirm_and_records(
    client, auth_header, candidate_a, resume_a, job_a, db_session
):
    other = Resume(
        user_id=str(candidate_a.id),
        raw_text="Candidate A resume v2",
        parsed_json={"name": "Candidate A", "expected_job_title": "后端工程师"},
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    apply_res = await client.post(
        "/applications",
        headers=auth_header(candidate_a),
        json={"job_id": str(job_a.id), "resume_id": str(resume_a.id)},
    )
    app_id = apply_res.json()["application"]["id"]
    initial_before = apply_res.json()["application"]["initial_submission_snapshot"]

    # 未确认应失败
    no_confirm = await client.patch(
        f"/applications/{app_id}/resume",
        headers=auth_header(candidate_a),
        json={"resume_id": str(other.id), "confirm": False},
    )
    assert no_confirm.status_code == 400

    # 确认后成功并留痕
    ok = await client.patch(
        f"/applications/{app_id}/resume",
        headers=auth_header(candidate_a),
        json={"resume_id": str(other.id), "confirm": True, "reason": "更新版本"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["application"]["resume_id"] == str(other.id)
    assert ok.json()["application"]["initial_submission_snapshot"] == initial_before
    assert ok.json()["application"]["current_resume_version_id"] == "v2"

    record = ok.json()["resume_change"]
    assert record["from_resume_id"] == str(resume_a.id)
    assert record["to_resume_id"] == str(other.id)
    assert record["actor_id"] == str(candidate_a.id)
    assert record["from_hash"] == initial_before["content_hash"]
    assert record["to_hash"]


async def test_pool_clarification_with_other_resume_conflicts(
    client, auth_header, candidate_a, employer_a, resume_a, job_a, db_session
):
    # 候选人先用 resume_a 投递
    apply_res = await client.post(
        "/applications",
        headers=auth_header(candidate_a),
        json={"job_id": str(job_a.id), "resume_id": str(resume_a.id)},
    )
    assert apply_res.status_code == 200

    # 另一份简历
    other = Resume(
        user_id=str(candidate_a.id),
        raw_text="Candidate A resume v2",
        parsed_json={
            "name": "Candidate A",
            "expected_job_title": "后端工程师",
            "work_experience": [],
        },
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    # 招聘方基于另一份简历发起澄清 → 冲突
    res = await client.post(
        f"/applications/job/{job_a.id}/resume/{other.id}/clarification-requests",
        headers=auth_header(employer_a),
        json={
            "claim_text": "负责订单模块开发",
            "questions": ["请补充指标？"],
        },
    )
    assert res.status_code == 409, res.text


async def test_match_only_pool_actions_are_denied_without_side_effects(
    client,
    auth_header,
    employer_a,
    candidate_a,
    resume_a,
    job_a,
    match_a,
    db_session,
):
    async def counts():
        values = []
        for model in (JobApplication, InterviewInvitation, ApplicationMessage):
            values.append(
                (await db_session.execute(select(func.count()).select_from(model))).scalar_one()
            )
        return tuple(values)

    before = await counts()
    clarification = await client.post(
        f"/applications/job/{job_a.id}/resume/{resume_a.id}/clarification-requests",
        headers=auth_header(employer_a),
        json={
            "claim_id": "work_experience_0_action_0",
            "claim_text": "负责订单模块开发",
            "questions": ["请补充指标？"],
        },
    )
    assert clarification.status_code == 404, clarification.text

    invitation = await client.post(
        "/invitations/send",
        headers=auth_header(employer_a),
        json={
            "job_id": str(job_a.id),
            "resume_id": str(resume_a.id),
            "message": "无授权邀请",
        },
    )
    assert invitation.status_code == 404, invitation.text

    audit = await client.get(
        f"/applications/job/{job_a.id}/resume/{resume_a.id}/credibility-audit",
        headers=auth_header(employer_a),
    )
    assert audit.status_code == 404, audit.text
    assert await counts() == before


async def test_cross_tenant_pool_actions_use_same_denial_and_no_side_effects(
    client,
    auth_header,
    employer_a,
    resume_b,
    job_a,
    db_session,
):
    async def counts():
        values = []
        for model in (JobApplication, InterviewInvitation, ApplicationMessage):
            result = await db_session.execute(select(func.count()).select_from(model))
            values.append(result.scalar_one())
        return tuple(values)

    before = await counts()
    clarification = await client.post(
        f"/applications/job/{job_a.id}/resume/{resume_b.id}/clarification-requests",
        headers=auth_header(employer_a),
        json={"claim_text": "跨租户主张", "questions": ["请说明？"]},
    )
    invitation = await client.post(
        "/invitations/send",
        headers=auth_header(employer_a),
        json={
            "job_id": str(job_a.id),
            "resume_id": str(resume_b.id),
            "message": "跨租户邀请",
        },
    )
    missing = await client.post(
        f"/applications/job/{job_a.id}/resume/not-a-real-resume/clarification-requests",
        headers=auth_header(employer_a),
        json={"claim_text": "不存在主张", "questions": ["请说明？"]},
    )
    assert clarification.status_code == invitation.status_code == missing.status_code == 404
    assert clarification.json()["detail"] == invitation.json()["detail"] == missing.json()["detail"]
    assert await counts() == before


async def test_open_claim_blocks_invitation_without_side_effects(
    client,
    auth_header,
    employer_a,
    application_a,
    resume_a,
    job_a,
    db_session,
):
    before = (
        await db_session.execute(select(func.count()).select_from(InterviewInvitation))
    ).scalar_one()
    res = await client.post(
        "/invitations/send",
        headers=auth_header(employer_a),
        json={
            "job_id": str(job_a.id),
            "resume_id": str(resume_a.id),
            "application_id": str(application_a.id),
            "message": "不应创建",
        },
    )
    assert res.status_code == 409, res.text
    await db_session.refresh(application_a)
    assert application_a.status == "needs_clarification"
    after = (
        await db_session.execute(select(func.count()).select_from(InterviewInvitation))
    ).scalar_one()
    assert after == before


async def test_invitation_is_atomic_and_pending_request_is_idempotent(
    client,
    auth_header,
    employer_b,
    application_b,
    resume_b,
    job_b,
    db_session,
):
    payload = {
        "job_id": str(job_b.id),
        "resume_id": str(resume_b.id),
        "application_id": str(application_b.id),
        "message": "合法邀请",
        "idempotency_key": "invite-request-1",
    }
    first = await client.post(
        "/invitations/send",
        headers=auth_header(employer_b),
        json=payload,
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        "/invitations/send",
        headers=auth_header(employer_b),
        json=payload,
    )
    assert second.status_code == 200, second.text
    assert second.json()["invitation_id"] == first.json()["invitation_id"]

    await db_session.refresh(application_b)
    assert application_b.status == "interview_invited"
    invitations = (
        (
            await db_session.execute(
                select(InterviewInvitation).where(
                    InterviewInvitation.application_id == str(application_b.id)
                )
            )
        )
        .scalars()
        .all()
    )
    messages = (
        (
            await db_session.execute(
                select(ApplicationMessage).where(
                    ApplicationMessage.application_id == str(application_b.id),
                    ApplicationMessage.message_kind == "interview_invite",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(invitations) == len(messages) == 1
    assert messages[0].message_meta["invitation_id"] == str(invitations[0].id)
    history = (application_b.pipeline_meta or {}).get("status_history", [])
    assert history[-1]["action"] == "create_invitation"
    assert history[-1]["request_key"] == "invite-request-1"


async def test_invitation_database_failure_rolls_back_all_core_records(
    client,
    auth_header,
    employer_b,
    application_b,
    resume_b,
    job_b,
    db_session,
    monkeypatch,
):
    original_commit = AsyncSession.commit

    async def fail_commit(self):
        raise RuntimeError("forced invitation commit failure")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="forced invitation commit failure"):
        await client.post(
            "/invitations/send",
            headers=auth_header(employer_b),
            json={
                "job_id": str(job_b.id),
                "resume_id": str(resume_b.id),
                "application_id": str(application_b.id),
                "message": "应整体回滚",
            },
        )
    monkeypatch.setattr(AsyncSession, "commit", original_commit)

    await db_session.refresh(application_b)
    assert application_b.status == "submitted"
    invitation_count = (
        await db_session.execute(select(func.count()).select_from(InterviewInvitation))
    ).scalar_one()
    message_count = (
        await db_session.execute(
            select(func.count())
            .select_from(ApplicationMessage)
            .where(ApplicationMessage.message_kind == "interview_invite")
        )
    ).scalar_one()
    assert invitation_count == message_count == 0
    assert (application_b.pipeline_meta or {}).get("status_history", []) == []


async def test_viewed_application_cannot_replace_resume_or_append_version(
    client,
    auth_header,
    candidate_b,
    employer_b,
    application_b,
    resume_b,
    job_b,
    db_session,
):
    other = Resume(
        user_id=str(candidate_b.id),
        raw_text="Candidate B replacement",
        parsed_json={"name": "Candidate B v2", "work_experience": []},
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    viewed = await client.get(
        f"/applications/{application_b.id}/messages",
        headers=auth_header(employer_b),
    )
    assert viewed.status_code == 200
    replacement = await client.patch(
        f"/applications/{application_b.id}/resume",
        headers=auth_header(candidate_b),
        json={"resume_id": str(other.id), "confirm": True},
    )
    assert replacement.status_code == 409
    await db_session.refresh(application_b)
    assert application_b.resume_id == str(resume_b.id)
    assert len((application_b.pipeline_meta or {})["resume_versions"]) == 1


async def test_audit_uses_and_persists_application_version_snapshot(
    client,
    auth_header,
    employer_b,
    application_b,
    resume_b,
    db_session,
):
    changed = dict(resume_b.parsed_json)
    changed["name"] = "mutated live resume"
    resume_b.parsed_json = changed
    await db_session.commit()

    audit = await client.get(
        f"/applications/{application_b.id}/credibility-audit",
        headers=auth_header(employer_b),
    )
    assert audit.status_code == 200, audit.text
    payload = audit.json()
    assert payload["candidate_name"] == "Candidate B"
    assert payload["application_resume_version_id"] == "v1"
    assert payload["snapshot_status"] == "reliable"

    history = await client.get(
        f"/applications/{application_b.id}/audit-history",
        headers=auth_header(employer_b),
    )
    assert history.status_code == 200
    stored = history.json()[0]["report"]["application_resume_snapshot"]
    assert stored["version_id"] == "v1"
    assert stored["parsed_json"]["name"] == "Candidate B"
