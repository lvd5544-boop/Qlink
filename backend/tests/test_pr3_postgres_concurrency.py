"""PR3 PostgreSQL-only concurrency and locking verification.

Run with an isolated database whose name contains ``jobplatform_test``:

    TEST_DATABASE_URL=postgresql+asyncpg://.../jobplatform_test \
      .venv/bin/python -m pytest -q -m postgresql \
      tests/test_pr3_postgres_concurrency.py

These tests intentionally fail instead of falling back to SQLite.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application_routes import _lock_application_identity
from app.models_db import ApplicationMessage, InterviewInvitation, JobApplication, Resume


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration,
    pytest.mark.postgresql,
]


@pytest.fixture(autouse=True)
async def require_postgresql(test_engine):
    assert test_engine.dialect.name == "postgresql", (
        "PR3 concurrency tests require PostgreSQL; SQLite fallback is forbidden"
    )
    async with test_engine.connect() as conn:
        database_name = (await conn.execute(text("SELECT current_database()"))).scalar_one()
    assert "jobplatform_test" in database_name


@pytest.fixture(autouse=True)
def disable_external_email(monkeypatch):
    async def _noop_send_email(*_args, **_kwargs):
        return True

    monkeypatch.setattr("app.application_routes.send_email", _noop_send_email)
    monkeypatch.setattr("app.invitation_routes.send_email", _noop_send_email)


async def _refresh_application(db_session, application_id: str) -> JobApplication:
    db_session.expire_all()
    app = await db_session.get(JobApplication, application_id)
    assert app is not None
    await db_session.refresh(app)
    return app


async def test_application_identity_advisory_lock_is_held(test_engine):
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            await _lock_application_identity(
                session,
                job_id="pg-lock-job",
                candidate_id="pg-lock-candidate",
            )
            held_count = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM pg_locks "
                        "WHERE locktype = 'advisory' AND pid = pg_backend_pid()"
                    )
                )
            ).scalar_one()
            assert held_count >= 1


async def test_two_different_claim_replies_are_both_preserved(
    client, auth_header, candidate_a, application_a, db_session
):
    claim_ids = [
        "work_experience_0_action_0",
        "work_experience_0_action_1",
    ]

    responses = await asyncio.gather(
        *[
            client.post(
                f"/applications/{application_a.id}/clarification-response",
                headers=auth_header(candidate_a),
                json={"claim_id": claim_id, "body": f"并发回复 {claim_id}"},
            )
            for claim_id in claim_ids
        ]
    )

    assert [response.status_code for response in responses] == [200, 200]
    app = await _refresh_application(db_session, str(application_a.id))
    threads = (app.pipeline_meta or {}).get("claim_threads") or {}
    assert {thread["status"] for thread in threads.values()} == {"answered"}
    assert all(thread.get("response_message_id") for thread in threads.values())
    assert app.status == "clarified"
    history = (app.pipeline_meta or {}).get("status_history") or []
    assert [item["to"] for item in history] == ["clarified"]

    response_count = (
        await db_session.execute(
            select(func.count())
            .select_from(ApplicationMessage)
            .where(
                ApplicationMessage.application_id == str(application_a.id),
                ApplicationMessage.message_kind == "clarification_response",
            )
        )
    ).scalar_one()
    assert response_count == 2


async def test_last_reply_racing_employer_close_has_one_winner_and_consistent_state(
    client, auth_header, candidate_a, employer_a, application_a, db_session
):
    first = await client.post(
        f"/applications/{application_a.id}/clarification-response",
        headers=auth_header(candidate_a),
        json={
            "claim_id": "work_experience_0_action_0",
            "body": "先回答第一条",
        },
    )
    assert first.status_code == 200

    reply, close = await asyncio.gather(
        client.post(
            f"/applications/{application_a.id}/clarification-response",
            headers=auth_header(candidate_a),
            json={
                "claim_id": "work_experience_0_action_1",
                "body": "并发回答最后一条",
            },
        ),
        client.post(
            f"/applications/{application_a.id}/clarification/close",
            headers=auth_header(employer_a),
            json={"reason": "并发验收关闭"},
        ),
    )

    assert sorted([reply.status_code, close.status_code]) == [200, 400]
    app = await _refresh_application(db_session, str(application_a.id))
    threads = (app.pipeline_meta or {}).get("claim_threads") or {}
    statuses = [thread.get("status") for thread in threads.values()]
    history = (app.pipeline_meta or {}).get("status_history") or []

    if reply.status_code == 200:
        assert app.status == "clarified"
        assert statuses.count("answered") == 2
        assert [item["to"] for item in history] == ["clarified"]
    else:
        assert app.status == "clarification_closed"
        assert statuses.count("answered") == 1
        assert statuses.count("closed") == 1
        assert [item["to"] for item in history] == ["clarification_closed"]


async def test_concurrent_duplicate_invitation_creates_one_pending_resource(
    client,
    auth_header,
    employer_b,
    resume_b,
    job_b,
    application_b,
    db_session,
):
    payload = {
        "job_id": str(job_b.id),
        "resume_id": str(resume_b.id),
        "application_id": str(application_b.id),
        "message": "并发邀请",
        "idempotency_key": "pg-concurrent-invite-1",
    }
    responses = await asyncio.gather(
        *[
            client.post(
                "/invitations/send",
                headers=auth_header(employer_b),
                json=payload,
            )
            for _ in range(2)
        ]
    )

    assert [response.status_code for response in responses] == [200, 200]
    assert {response.json()["status"] for response in responses} == {"ok", "exists"}
    invitation_ids = {response.json()["invitation_id"] for response in responses}
    assert len(invitation_ids) == 1

    invitation_count = (
        await db_session.execute(
            select(func.count())
            .select_from(InterviewInvitation)
            .where(
                InterviewInvitation.application_id == str(application_b.id),
                InterviewInvitation.status == "pending",
            )
        )
    ).scalar_one()
    message_count = (
        await db_session.execute(
            select(func.count())
            .select_from(ApplicationMessage)
            .where(
                ApplicationMessage.application_id == str(application_b.id),
                ApplicationMessage.message_kind == "interview_invite",
            )
        )
    ).scalar_one()
    assert invitation_count == 1
    assert message_count == 1


async def test_concurrent_duplicate_apply_creates_one_application(
    client, auth_header, candidate_a, resume_a, job_a, db_session
):
    payload = {"job_id": str(job_a.id), "resume_id": str(resume_a.id)}
    responses = await asyncio.gather(
        *[
            client.post(
                "/applications",
                headers=auth_header(candidate_a),
                json=payload,
            )
            for _ in range(2)
        ]
    )

    assert [response.status_code for response in responses] == [200, 200]
    application_ids = {response.json()["application"]["id"] for response in responses}
    assert len(application_ids) == 1
    assert {response.json()["status"] for response in responses} == {"ok", "exists"}

    application_count = (
        await db_session.execute(
            select(func.count())
            .select_from(JobApplication)
            .where(
                JobApplication.job_id == str(job_a.id),
                JobApplication.candidate_id == str(candidate_a.id),
            )
        )
    ).scalar_one()
    assert application_count == 1


async def test_concurrent_explicit_resume_changes_append_unique_versions(
    client,
    auth_header,
    candidate_b,
    application_b,
    db_session,
):
    replacements = [
        Resume(
            user_id=str(candidate_b.id),
            raw_text=f"replacement {index}",
            parsed_json={"summary": f"并发版本 {index}"},
        )
        for index in (2, 3)
    ]
    db_session.add_all(replacements)
    await db_session.commit()
    for resume in replacements:
        await db_session.refresh(resume)
    replacement_ids = {str(resume.id) for resume in replacements}

    responses = await asyncio.gather(
        *[
            client.patch(
                f"/applications/{application_b.id}/resume",
                headers=auth_header(candidate_b),
                json={
                    "resume_id": str(resume.id),
                    "confirm": True,
                    "reason": "PostgreSQL 并发版本验收",
                },
            )
            for resume in replacements
        ]
    )

    assert [response.status_code for response in responses] == [200, 200]
    app = await _refresh_application(db_session, str(application_b.id))
    versions = (app.pipeline_meta or {}).get("resume_versions") or []
    version_ids = [version["version_id"] for version in versions]
    assert version_ids == ["v1", "v2", "v3"]
    assert len(version_ids) == len(set(version_ids))
    assert {version["resume_id"] for version in versions[1:]} == replacement_ids
    assert (app.pipeline_meta or {}).get("current_resume_version_id") == "v3"
    assert len((app.pipeline_meta or {}).get("resume_change_history") or []) == 2


async def test_duplicate_same_claim_race_leaves_no_partial_side_effects(
    client, auth_header, candidate_a, application_a, db_session
):
    payload = {
        "claim_id": "work_experience_0_action_0",
        "body": "同一 Claim 并发回复",
    }
    responses = await asyncio.gather(
        *[
            client.post(
                f"/applications/{application_a.id}/clarification-response",
                headers=auth_header(candidate_a),
                json=payload,
            )
            for _ in range(2)
        ]
    )

    assert sorted(response.status_code for response in responses) == [200, 400]
    app = await _refresh_application(db_session, str(application_a.id))
    threads = (app.pipeline_meta or {}).get("claim_threads") or {}
    assert threads["work_experience_0_action_0"]["status"] == "answered"
    assert threads["work_experience_0_action_1"]["status"] == "open"
    assert app.status == "needs_clarification"
    assert (app.pipeline_meta or {}).get("status_history") in (None, [])

    response_count = (
        await db_session.execute(
            select(func.count())
            .select_from(ApplicationMessage)
            .where(
                ApplicationMessage.application_id == str(application_a.id),
                ApplicationMessage.message_kind == "clarification_response",
            )
        )
    ).scalar_one()
    invitation_count = (
        await db_session.execute(
            select(func.count())
            .select_from(InterviewInvitation)
            .where(InterviewInvitation.application_id == str(application_a.id))
        )
    ).scalar_one()
    assert response_count == 1
    assert invitation_count == 0
