from sqlalchemy import func, select

from app.models_db import PilotConsent, PilotFeedback, PilotParticipant, User


async def _count(db, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def test_candidate_controls_independent_pilot_consent(
    client, auth_header, db_session, candidate_a
):
    initial = await client.get("/pilot/me", headers=auth_header(candidate_a))
    assert initial.status_code == 200
    assert initial.json()["status"] == "not_enrolled"
    assert initial.json()["model_improvement"] is False

    headers = {**auth_header(candidate_a), "Idempotency-Key": "pilot-consent-1"}
    accepted = await client.post(
        "/pilot/consent",
        headers=headers,
        json={
            "product_research": True,
            "aggregate_metrics": True,
            "model_improvement": False,
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["enrolled"] is True
    assert accepted.json()["aggregate_metrics"] is True
    assert accepted.json()["model_improvement"] is False
    assert accepted.json()["participant_code"]

    replay = await client.post(
        "/pilot/consent",
        headers=headers,
        json={
            "product_research": True,
            "aggregate_metrics": True,
            "model_improvement": False,
        },
    )
    assert replay.status_code == 200
    assert replay.json() == accepted.json()
    assert await _count(db_session, PilotParticipant) == 1
    assert await _count(db_session, PilotConsent) == 1


async def test_pilot_rejects_bundled_or_non_candidate_consent(
    client, auth_header, candidate_a, employer_a
):
    missing_research = await client.post(
        "/pilot/consent",
        headers=auth_header(candidate_a),
        json={"product_research": False, "model_improvement": True},
    )
    assert missing_research.status_code == 422

    employer = await client.get("/pilot/me", headers=auth_header(employer_a))
    assert employer.status_code == 403


async def test_feedback_requires_active_consent_and_is_replay_safe(
    client, auth_header, db_session, candidate_a
):
    payload = {
        "category": "usability",
        "rating": 4,
        "context": "/candidate/advisor",
        "message": "The next action was clear.",
        "allow_follow_up": False,
    }
    blocked = await client.post("/pilot/feedback", headers=auth_header(candidate_a), json=payload)
    assert blocked.status_code == 409

    await client.post(
        "/pilot/consent",
        headers=auth_header(candidate_a),
        json={"product_research": True},
    )
    headers = {**auth_header(candidate_a), "Idempotency-Key": "pilot-feedback-1"}
    created = await client.post("/pilot/feedback", headers=headers, json=payload)
    replay = await client.post("/pilot/feedback", headers=headers, json=payload)
    assert created.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == created.json()
    assert await _count(db_session, PilotFeedback) == 1


async def test_withdraw_stops_feedback_and_account_deletion_cascades(
    client, auth_header, db_session, candidate_a
):
    await client.post(
        "/pilot/consent",
        headers=auth_header(candidate_a),
        json={"product_research": True, "model_improvement": True},
    )
    withdrawn = await client.post("/pilot/withdraw", headers=auth_header(candidate_a))
    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "withdrawn"
    assert withdrawn.json()["model_improvement"] is False

    feedback = await client.post(
        "/pilot/feedback",
        headers=auth_header(candidate_a),
        json={
            "category": "other",
            "rating": 3,
            "message": "Should no longer be accepted.",
        },
    )
    assert feedback.status_code == 409

    deleted = await client.delete("/auth/account", headers=auth_header(candidate_a))
    assert deleted.status_code == 200
    assert await _count(db_session, PilotParticipant) == 0
    user_count = (
        await db_session.execute(
            select(func.count()).select_from(User).where(User.id == str(candidate_a.id))
        )
    ).scalar_one()
    assert user_count == 0
