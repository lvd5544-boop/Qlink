"""PR12 DoD gates for structured interview sessions."""

from __future__ import annotations

from app.claim_passport import sync_resume_claims
from app.interview_policy import (
    assert_question_allowed,
    extract_observations_from_answer,
    is_sensitive_question,
    plan_core_questions,
    plan_probe_question,
    validate_observation_offsets,
)
from app.models_db import ClaimEvent, JobDescription, ResumeClaim


async def _sync_claim(db_session, resume, actor_id):
    claims = await sync_resume_claims(
        db_session, resume, actor_id=str(actor_id), reason="pr12_test"
    )
    await db_session.commit()
    return claims[0]


def test_sensitive_questions_are_blocked():
    assert is_sensitive_question("你今年多大年龄？")
    assert is_sensitive_question("是否计划结婚生育？")
    try:
        assert_question_allowed("请说明你的民族和籍贯")
        assert False, "expected ban"
    except ValueError as exc:
        assert str(exc) == "sensitive_or_discriminatory_question"
    assert not is_sensitive_question("请说明该指标的统计口径")


def test_observation_offsets_round_trip_to_answer_text():
    answer = "我负责订单模块，把接口延迟降低了 35%。"
    observations = extract_observations_from_answer(answer)
    assert observations
    for item in observations:
        assert validate_observation_offsets(
            answer, item["source_start"], item["source_end"], item["text"]
        )
        assert answer[item["source_start"] : item["source_end"]] == item["text"]


def test_same_job_core_questions_are_deterministic(job_a):
    first = plan_core_questions(mode="target_gap", job=job_a)
    second = plan_core_questions(mode="target_gap", job=job_a)
    assert [item.question_text for item in first] == [item.question_text for item in second]
    assert all(item.question_goal == "job_requirement" for item in first)


def test_repeated_probe_terminates():
    class Claim:
        id = "c1"
        current_text = "把接口延迟降低了 35%"
        claim_type = "result"

    assert (
        plan_probe_question(claim=Claim(), prior_probe_count=2, last_goal="clarify_metric") is None
    )
    assert (
        plan_probe_question(claim=Claim(), prior_probe_count=0, last_goal="clarify_metric")
        is not None
    )


async def test_practice_answers_do_not_auto_become_claims(
    client, db_session, candidate_a, resume_a, auth_header
):
    claim = await _sync_claim(db_session, resume_a, candidate_a.id)
    created = await client.post(
        "/interview-sessions",
        json={
            "mode": "practice",
            "resume_id": str(resume_a.id),
            "consent_snapshot": {"resume_write": True},
        },
        headers=auth_header(candidate_a),
    )
    assert created.status_code == 200, created.text
    session = created.json()["session"]
    question = session["questions"][0]
    answered = await client.post(
        f"/interview-sessions/{session['id']}/answers",
        json={
            "question_id": question["id"],
            "answer_text": "我在模拟场景中把吞吐提升了 20%。",
        },
        headers=auth_header(candidate_a),
    )
    assert answered.status_code == 200, answered.text
    observation_id = answered.json()["observations"][0]["id"]
    confirmed = await client.post(
        f"/interview-observations/{observation_id}/confirm",
        headers=auth_header(candidate_a),
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["writeback"] == "blocked"
    assert confirmed.json()["writeback_reason"] == "practice_isolated"
    from sqlalchemy import select

    rows = (
        (
            await db_session.execute(
                select(ClaimEvent).where(
                    ClaimEvent.event_type == "interview_observation_confirmed",
                    ClaimEvent.claim_id == str(claim.id),
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows == []


async def test_unconfirmed_observation_cannot_write_resume(
    client, db_session, candidate_a, resume_a, auth_header
):
    claim = await _sync_claim(db_session, resume_a, candidate_a.id)
    created = await client.post(
        "/interview-sessions",
        json={
            "mode": "claim_clarification",
            "claim_id": str(claim.id),
            "resume_id": str(resume_a.id),
            "consent_snapshot": {"resume_write": True},
        },
        headers=auth_header(candidate_a),
    )
    assert created.status_code == 200, created.text
    session = created.json()["session"]
    question = session["questions"][0]
    answered = await client.post(
        f"/interview-sessions/{session['id']}/answers",
        json={
            "question_id": question["id"],
            "answer_text": "该指标来自线上监控，统计口径是 P99 延迟。",
        },
        headers=auth_header(candidate_a),
    )
    assert answered.status_code == 200
    observation = answered.json()["observations"][0]
    assert observation["candidate_confirmation_state"] == "pending"
    assert observation["offset_valid"] is True

    from app.interview_sessions import apply_confirmed_observation_to_claim, owned_session
    from app.models_db import InterviewObservation

    session_row = await owned_session(db_session, session["id"], str(candidate_a.id))
    obs_row = await db_session.get(InterviewObservation, observation["id"])
    try:
        await apply_confirmed_observation_to_claim(
            db_session,
            session=session_row,
            observation=obs_row,
            actor_id=str(candidate_a.id),
        )
        assert False, "expected unconfirmed block"
    except PermissionError as exc:
        assert str(exc) == "observation_unconfirmed"


async def test_confirmed_observation_can_write_non_practice_claim(
    client, db_session, candidate_a, resume_a, auth_header
):
    claim = await _sync_claim(db_session, resume_a, candidate_a.id)
    created = await client.post(
        "/interview-sessions",
        json={
            "mode": "claim_clarification",
            "claim_id": str(claim.id),
            "consent_snapshot": {"resume_write": True},
        },
        headers=auth_header(candidate_a),
    )
    session = created.json()["session"]
    question = session["questions"][0]
    answered = await client.post(
        f"/interview-sessions/{session['id']}/answers",
        json={
            "question_id": question["id"],
            "answer_text": "我负责压测脚本，把接口延迟降低了 35%。",
        },
        headers=auth_header(candidate_a),
    )
    observation_id = answered.json()["observations"][0]["id"]
    confirmed = await client.post(
        f"/interview-observations/{observation_id}/confirm",
        headers=auth_header(candidate_a),
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["writeback"] == "applied"
    assert confirmed.json()["claim_id"] == str(claim.id)
    refreshed = await db_session.get(ResumeClaim, str(claim.id))
    await db_session.refresh(refreshed)
    assert refreshed.evidence_state == "supported_by_user_evidence"


async def test_revoke_stops_further_answers(client, db_session, candidate_a, resume_a, auth_header):
    created = await client.post(
        "/interview-sessions",
        json={"mode": "vault_builder", "resume_id": str(resume_a.id)},
        headers=auth_header(candidate_a),
    )
    session = created.json()["session"]
    revoked = await client.post(
        f"/interview-sessions/{session['id']}/revoke",
        headers=auth_header(candidate_a),
    )
    assert revoked.status_code == 200
    assert revoked.json()["session"]["status"] == "revoked"
    blocked = await client.post(
        f"/interview-sessions/{session['id']}/answers",
        json={
            "question_id": session["questions"][0]["id"],
            "answer_text": "不应再被接受",
        },
        headers=auth_header(candidate_a),
    )
    assert blocked.status_code == 409


async def test_claim_chat_uses_same_clarification_service(
    client, db_session, candidate_a, resume_a, auth_header
):
    claim = await _sync_claim(db_session, resume_a, candidate_a.id)
    response = await client.post(
        f"/career-passport/claims/{claim.id}/chat/messages",
        json={"body": "我想补充口径说明", "question_goal": "clarify", "ai_enabled": True},
        headers=auth_header(candidate_a),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ai_connected"] is False
    assert payload["clarification_connected"] is True
    assert payload["generated_by"] == "rules"
    assert payload["assistant_message"]["question_goal"]
    assert payload["session_id"]

    disabled = await client.post(
        f"/career-passport/claims/{claim.id}/chat/messages",
        json={"body": "先不开启 AI", "question_goal": "clarify", "ai_enabled": False},
        headers=auth_header(candidate_a),
    )
    assert disabled.status_code == 200
    assert disabled.json()["ai_connected"] is False
    assert disabled.json()["clarification_connected"] is False


async def test_target_gap_sessions_share_core_question_bank(
    client, candidate_a, resume_a, job_a, auth_header
):
    first = await client.post(
        "/interview-sessions",
        json={
            "mode": "target_gap",
            "job_id": str(job_a.id),
            "resume_id": str(resume_a.id),
        },
        headers=auth_header(candidate_a),
    )
    second = await client.post(
        "/interview-sessions",
        json={
            "mode": "target_gap",
            "job_id": str(job_a.id),
            "resume_id": str(resume_a.id),
        },
        headers=auth_header(candidate_a),
    )
    assert first.status_code == 200 and second.status_code == 200
    q1 = [item["question_text"] for item in first.json()["session"]["questions"]]
    q2 = [item["question_text"] for item in second.json()["session"]["questions"]]
    assert q1 == q2
    assert q1


async def test_answer_cannot_expand_session_consent(client, candidate_a, resume_a, auth_header):
    created = await client.post(
        "/interview-sessions",
        json={
            "mode": "vault_builder",
            "resume_id": str(resume_a.id),
            "consent_snapshot": {
                "resume_write": False,
                "job_recommendation": False,
                "employer_share": False,
                "model_improvement": False,
            },
        },
        headers=auth_header(candidate_a),
    )
    assert created.status_code == 200, created.text
    session = created.json()["session"]
    answered = await client.post(
        f"/interview-sessions/{session['id']}/answers",
        json={
            "question_id": session["questions"][0]["id"],
            "answer_text": "我负责订单系统改造，延迟下降 20%。",
            "allowed_uses": {
                "resume_write": True,
                "job_recommendation": True,
                "employer_share": True,
                "model_improvement": True,
            },
            "share_with_employer": True,
        },
        headers=auth_header(candidate_a),
    )
    assert answered.status_code == 200, answered.text
    uses = answered.json()["answer"]["allowed_uses"]
    assert uses == {
        "resume_write": False,
        "job_recommendation": False,
        "employer_share": False,
        "model_improvement": False,
    }
    assert answered.json()["answer"]["share_with_employer"] is False


async def test_target_gap_requires_job_id(client, candidate_a, resume_a, auth_header):
    response = await client.post(
        "/interview-sessions",
        json={"mode": "target_gap", "resume_id": str(resume_a.id)},
        headers=auth_header(candidate_a),
    )
    assert response.status_code == 422
    assert "job_id" in response.json()["detail"]


async def test_target_gap_rejects_another_candidates_private_job(
    client, db_session, candidate_a, candidate_b, resume_a, auth_header
):
    private_job = JobDescription(
        employer_id=None,
        title="候选人 B 的私有面试目标",
        raw_text="Python 后端工程师",
        parsed_json={
            "advisor_private": True,
            "advisor_imported_by": str(candidate_b.id),
            "required_skills": ["Python"],
        },
    )
    db_session.add(private_job)
    await db_session.commit()

    response = await client.post(
        "/interview-sessions",
        json={
            "mode": "target_gap",
            "resume_id": str(resume_a.id),
            "job_id": str(private_job.id),
        },
        headers=auth_header(candidate_a),
    )

    assert response.status_code == 404


async def test_revoke_clears_purpose_consent_and_blocks_writeback(
    client, db_session, candidate_a, resume_a, auth_header
):
    created = await client.post(
        "/interview-sessions",
        json={
            "mode": "vault_builder",
            "resume_id": str(resume_a.id),
            "consent_snapshot": {"resume_write": True, "employer_share": True},
        },
        headers=auth_header(candidate_a),
    )
    session = created.json()["session"]
    answered = await client.post(
        f"/interview-sessions/{session['id']}/answers",
        json={
            "question_id": session["questions"][0]["id"],
            "answer_text": "我主导了库存同步改造，故障率下降 15%。",
            "share_with_employer": True,
        },
        headers=auth_header(candidate_a),
    )
    assert answered.status_code == 200
    observation_id = answered.json()["observations"][0]["id"]
    assert answered.json()["answer"]["share_with_employer"] is True

    revoked = await client.post(
        f"/interview-sessions/{session['id']}/revoke",
        headers=auth_header(candidate_a),
    )
    assert revoked.status_code == 200
    assert revoked.json()["session"]["status"] == "revoked"
    assert revoked.json()["session"]["consent_snapshot"]["resume_write"] is False
    assert revoked.json()["session"]["consent_snapshot"]["employer_share"] is False

    from app.models_db import InterviewAnswer, InterviewObservation

    obs = await db_session.get(InterviewObservation, observation_id)
    await db_session.refresh(obs)
    assert obs.candidate_confirmation_state == "rejected"
    answer = await db_session.get(InterviewAnswer, obs.answer_id)
    await db_session.refresh(answer)
    assert answer.share_with_employer is False
    assert answer.allowed_uses["resume_write"] is False

    blocked = await client.post(
        f"/interview-observations/{observation_id}/confirm",
        headers=auth_header(candidate_a),
    )
    assert blocked.status_code == 409


async def test_vault_builder_confirmation_writes_career_memory(
    client, db_session, candidate_a, resume_a, auth_header
):
    created = await client.post(
        "/interview-sessions",
        json={
            "mode": "vault_builder",
            "resume_id": str(resume_a.id),
            "consent_snapshot": {"resume_write": True},
        },
        headers=auth_header(candidate_a),
    )
    session = created.json()["session"]
    answered = await client.post(
        f"/interview-sessions/{session['id']}/answers",
        json={
            "question_id": session["questions"][0]["id"],
            "answer_text": "我在支付清算项目中负责对账链路，差错率下降 12%。",
        },
        headers=auth_header(candidate_a),
    )
    observation_id = answered.json()["observations"][0]["id"]
    confirmed = await client.post(
        f"/interview-observations/{observation_id}/confirm",
        headers=auth_header(candidate_a),
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["writeback"] == "applied"
    claim_id = confirmed.json()["claim_id"]
    assert claim_id
    claim = await db_session.get(ResumeClaim, claim_id)
    await db_session.refresh(claim)
    assert claim.origin_kind == "interview"
    assert claim.career_experience_id
    from app.models_db import CareerExperience

    experience = await db_session.get(CareerExperience, claim.career_experience_id)
    assert experience is not None
    assert "interview_session:" in (experience.source_ref or "")


async def test_completed_interview_keeps_transcript_and_candidate_feedback(
    client, candidate_a, resume_a, auth_header
):
    created = await client.post(
        "/interview-sessions",
        json={"mode": "practice", "resume_id": str(resume_a.id)},
        headers=auth_header(candidate_a),
    )
    session = created.json()["session"]
    answered = await client.post(
        f"/interview-sessions/{session['id']}/answers",
        json={
            "question_id": session["questions"][0]["id"],
            "answer_text": "我负责接口压测和缓存方案，把 P99 延迟降低了 35%，并复盘了容量估算。",
        },
        headers=auth_header(candidate_a),
    )
    assert answered.status_code == 200, answered.text
    completed = await client.post(
        f"/interview-sessions/{session['id']}/complete",
        headers=auth_header(candidate_a),
    )
    assert completed.status_code == 200, completed.text
    report = completed.json()["report"]
    assert report["transcript"][0]["answer_text"]
    assert report["strengths"]
    assert report["improvements"]
    assert report["personalized_coaching"]["personalization_basis"]["used_resume"] is True
    assert report["personalized_coaching"]["actions"]
    first_action = report["personalized_coaching"]["actions"][0]
    assert first_action["practice_prompt"]
    assert first_action["success_criteria"]
    assert first_action["based_on"]
    assert report["coaching_method"].startswith("任务标准")
    assert set(report["scores"]) == {
        "回答完整度",
        "个人贡献清晰度",
        "结果证据",
        "复盘深度",
    }

    history = await client.get(
        "/interview-sessions",
        headers=auth_header(candidate_a),
    )
    assert history.status_code == 200
    saved = next(item for item in history.json()["sessions"] if item["id"] == session["id"])
    assert saved["status"] == "completed"
    assert saved["report"]["transcript"][0]["answer_text"]


async def test_create_session_idempotency_replay(client, candidate_a, resume_a, auth_header):
    headers = {**auth_header(candidate_a), "Idempotency-Key": "pr12-create-1"}
    body = {
        "mode": "practice",
        "resume_id": str(resume_a.id),
        "consent_snapshot": {"resume_write": False},
    }
    first = await client.post("/interview-sessions", json=body, headers=headers)
    second = await client.post("/interview-sessions", json=body, headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["session"]["id"] == second.json()["session"]["id"]
