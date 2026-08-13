from __future__ import annotations

import pytest

from app.models_db import JobDescription


pytestmark = pytest.mark.asyncio


async def _private_job(db_session, candidate):
    job = JobDescription(
        employer_id=None,
        title="AI 产品经理",
        raw_text="负责 AI 产品规划与用户研究",
        parsed_json={
            "title": "AI 产品经理",
            "advisor_private": True,
            "advisor_imported_by": str(candidate.id),
            "location": "上海",
        },
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


async def test_candidate_records_external_application_and_outcomes(
    client, auth_header, candidate_a, resume_a, db_session
):
    job = await _private_job(db_session, candidate_a)
    created = await client.post(
        "/applications/external-tracking",
        headers=auth_header(candidate_a),
        json={"job_id": str(job.id), "resume_id": str(resume_a.id)},
    )
    assert created.status_code == 200, created.text
    application = created.json()["application"]
    assert application["external_tracking"] is True
    assert application["application_source"] == "candidate_external_tracking"
    assert application["status"] == "submitted"
    assert application["employer_id"] is None
    assert application["outcome_timeline"][0]["source"] == "candidate_reported"

    duplicate = await client.post(
        "/applications/external-tracking",
        headers=auth_header(candidate_a),
        json={"job_id": str(job.id), "resume_id": str(resume_a.id)},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "exists"
    assert duplicate.json()["application"]["id"] == application["id"]

    interview = await client.patch(
        f"/applications/external-tracking/{application['id']}/status",
        headers=auth_header(candidate_a),
        json={
            "status": "interview_invited",
            "occurred_at": application["created_at"],
            "feedback": "Recruiter invited me to a first-round interview.",
        },
    )
    assert interview.status_code == 200, interview.text
    assert interview.json()["application"]["status"] == "interview_invited"
    interview_event = interview.json()["application"]["outcome_timeline"][-1]
    assert interview_event["source"] == "candidate_reported"
    assert interview_event["raw_feedback"] == ("Recruiter invited me to a first-round interview.")
    assert interview_event["occurred_at"].startswith(application["created_at"][:19])

    accepted = await client.patch(
        f"/applications/external-tracking/{application['id']}/status",
        headers=auth_header(candidate_a),
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["application"]["status"] == "accepted"

    listed = await client.get(
        "/applications/mine/evaluations",
        headers=auth_header(candidate_a),
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["external_tracking"] is True


async def test_external_tracking_is_limited_to_owned_private_jobs(
    client, auth_header, candidate_a, candidate_b, resume_a, job_a, db_session
):
    private_job = await _private_job(db_session, candidate_a)
    public_denied = await client.post(
        "/applications/external-tracking",
        headers=auth_header(candidate_a),
        json={"job_id": str(job_a.id), "resume_id": str(resume_a.id)},
    )
    assert public_denied.status_code == 404

    other_candidate_denied = await client.post(
        "/applications/external-tracking",
        headers=auth_header(candidate_b),
        json={"job_id": str(private_job.id), "resume_id": str(resume_a.id)},
    )
    assert other_candidate_denied.status_code == 404
