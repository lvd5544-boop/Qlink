"""PR12 structured interview session domain service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .interview_policy import (
    DECLINE_REASONS,
    POLICY_VERSION,
    SESSION_MODES,
    extract_observations_from_answer,
    plan_core_questions,
    plan_probe_question,
    validate_observation_offsets,
)
from .personalized_guidance import build_interview_action_plan, guidance_context
from .models_db import (
    ClaimEvent,
    InterviewAnswer,
    InterviewObservation,
    InterviewQuestion,
    InterviewSession,
    JobDescription,
    Resume,
    ResumeClaim,
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _consent_defaults(snapshot: dict | None) -> dict[str, bool]:
    keys = ("resume_write", "job_recommendation", "employer_share", "model_improvement")
    source = snapshot or {}
    return {key: bool(source.get(key)) for key in keys}


def _intersect_consent(session_snapshot: dict | None, requested: dict | None) -> dict[str, bool]:
    """Answer-level uses may only shrink the session consent snapshot, never expand it."""
    baseline = _consent_defaults(session_snapshot)
    if not requested:
        return baseline
    asked = _consent_defaults(requested)
    return {key: bool(baseline.get(key) and asked.get(key)) for key in baseline}


def _share_allowed(session_snapshot: dict | None, requested_share: bool) -> bool:
    return bool(requested_share and (session_snapshot or {}).get("employer_share"))


async def owned_session(db: AsyncSession, session_id: str, user_id: str) -> InterviewSession | None:
    return (
        await db.execute(
            select(InterviewSession).where(
                InterviewSession.id == str(session_id),
                InterviewSession.user_id == str(user_id),
            )
        )
    ).scalar_one_or_none()


async def create_session(
    db: AsyncSession,
    *,
    user_id: str,
    mode: str,
    job_id: str | None = None,
    resume_id: str | None = None,
    claim_id: str | None = None,
    consent_snapshot: dict | None = None,
    ai_enabled: bool = True,
) -> InterviewSession:
    if mode not in SESSION_MODES:
        raise ValueError("invalid_mode")

    claim = None
    if claim_id:
        claim = await db.get(ResumeClaim, claim_id)
        if not claim or str(claim.user_id) != str(user_id):
            raise PermissionError("claim_not_owned")
    if mode == "claim_clarification" and claim is None:
        raise ValueError("claim_required")

    resume = None
    if resume_id:
        resume = await db.get(Resume, resume_id)
        if not resume or str(resume.user_id) != str(user_id):
            raise PermissionError("resume_not_owned")

    job = None
    if job_id:
        job = await db.get(JobDescription, job_id)
        if job is None:
            raise ValueError("job_not_found")
    if mode == "target_gap" and job is None:
        raise ValueError("job_required")
    if mode == "vault_builder" and resume is None and claim is None:
        # Career-memory writeback needs a resume container when available; allow
        # session creation without resume, but confirmation will require one.
        pass

    session = InterviewSession(
        id=str(uuid.uuid4()),
        user_id=str(user_id),
        mode=mode,
        job_id=str(job.id) if job else None,
        resume_id=str(resume.id) if resume else (str(claim.resume_id) if claim else None),
        claim_id=str(claim.id) if claim else None,
        status="active",
        consent_snapshot=_consent_defaults(consent_snapshot),
        policy_version=POLICY_VERSION,
        ai_enabled=bool(ai_enabled),
    )
    db.add(session)
    await db.flush()

    planned = plan_core_questions(
        mode=mode,
        claim=claim,
        resume_json=(resume.parsed_json if resume else None),
        job=job,
    )
    for index, item in enumerate(planned, start=1):
        db.add(
            InterviewQuestion(
                id=str(uuid.uuid4()),
                session_id=str(session.id),
                sequence_no=index,
                question_goal=item.question_goal,
                claim_id=item.claim_id,
                requirement_id=item.requirement_id,
                competency_id=item.competency_id,
                core_or_probe=item.core_or_probe,
                question_text=item.question_text,
                policy_version=POLICY_VERSION,
                generated_by="rules",
            )
        )
    await db.flush()
    return session


async def list_questions(db: AsyncSession, session_id: str) -> list[InterviewQuestion]:
    return (
        await db.execute(
            select(InterviewQuestion)
            .where(InterviewQuestion.session_id == str(session_id))
            .order_by(InterviewQuestion.sequence_no.asc())
        )
    ).scalars().all()


async def next_question(
    db: AsyncSession,
    session: InterviewSession,
) -> InterviewQuestion | None:
    if session.status != "active":
        raise RuntimeError("session_not_active")

    questions = await list_questions(db, str(session.id))
    answered_ids = set(
        (
            await db.execute(
                select(InterviewAnswer.question_id).where(
                    InterviewAnswer.question_id.in_([str(q.id) for q in questions] or ["__none__"])
                )
            )
        ).scalars().all()
    )
    for question in questions:
        if str(question.id) not in {str(value) for value in answered_ids}:
            return question

    # Optionally add a probe for claim clarification / target gap when unanswered probes remain.
    if session.mode in {"claim_clarification", "target_gap"} and session.claim_id:
        claim = await db.get(ResumeClaim, session.claim_id)
        probe_count = sum(1 for q in questions if q.core_or_probe == "probe")
        last_goal = questions[-1].question_goal if questions else None
        planned = plan_probe_question(
            claim=claim,
            prior_probe_count=probe_count,
            last_goal=last_goal,
        )
        if planned is None:
            return None
        question = InterviewQuestion(
            id=str(uuid.uuid4()),
            session_id=str(session.id),
            sequence_no=len(questions) + 1,
            question_goal=planned.question_goal,
            claim_id=planned.claim_id,
            requirement_id=planned.requirement_id,
            competency_id=planned.competency_id,
            core_or_probe=planned.core_or_probe,
            question_text=planned.question_text,
            policy_version=POLICY_VERSION,
            generated_by="rules",
        )
        db.add(question)
        await db.flush()
        return question
    return None


async def submit_answer(
    db: AsyncSession,
    *,
    session: InterviewSession,
    question_id: str,
    answer_text: str | None = None,
    user_declined: bool = False,
    decline_reason: str | None = None,
    allowed_uses: dict | None = None,
    share_with_employer: bool = False,
) -> tuple[InterviewAnswer, list[InterviewObservation]]:
    if session.status != "active":
        raise RuntimeError("session_not_active")
    if session.revoked_at is not None:
        raise RuntimeError("session_revoked")

    question = await db.get(InterviewQuestion, question_id)
    if not question or str(question.session_id) != str(session.id):
        raise PermissionError("question_not_in_session")

    existing = (
        await db.execute(
            select(InterviewAnswer).where(InterviewAnswer.question_id == str(question.id))
        )
    ).scalar_one_or_none()
    if existing:
        raise RuntimeError("answer_already_exists")

    if user_declined:
        if decline_reason and decline_reason not in DECLINE_REASONS:
            raise ValueError("invalid_decline_reason")
        text = ""
    else:
        text = (answer_text or "").strip()
        if not text:
            raise ValueError("answer_required")

    answer = InterviewAnswer(
        id=str(uuid.uuid4()),
        question_id=str(question.id),
        answer_text_snapshot=text,
        user_declined=bool(user_declined),
        decline_reason=decline_reason if user_declined else None,
        allowed_uses=_intersect_consent(session.consent_snapshot, allowed_uses),
        share_with_employer=_share_allowed(session.consent_snapshot, share_with_employer),
    )
    db.add(answer)
    await db.flush()

    observations: list[InterviewObservation] = []
    if not user_declined:
        for item in extract_observations_from_answer(
            text,
            claim_id=question.claim_id or session.claim_id,
            question_goal=question.question_goal,
        ):
            if not validate_observation_offsets(
                text, item["source_start"], item["source_end"], item["text"]
            ):
                continue
            # Never store LLM infer as confirmed.
            row = InterviewObservation(
                id=str(uuid.uuid4()),
                answer_id=str(answer.id),
                observation_type=item["observation_type"],
                text=item["text"],
                source_start=item["source_start"],
                source_end=item["source_end"],
                claim_id=item.get("claim_id"),
                candidate_confirmation_state="pending",
                extractor_version="rules_obs_v1",
            )
            db.add(row)
            observations.append(row)
        await db.flush()

    if user_declined and decline_reason == "stop_followup":
        session.status = "completed"
        session.completed_at = now_utc()

    return answer, observations


async def list_observations_for_session(
    db: AsyncSession, session_id: str
) -> list[InterviewObservation]:
    return (
        await db.execute(
            select(InterviewObservation)
            .join(InterviewAnswer, InterviewAnswer.id == InterviewObservation.answer_id)
            .join(InterviewQuestion, InterviewQuestion.id == InterviewAnswer.question_id)
            .where(InterviewQuestion.session_id == str(session_id))
            .order_by(InterviewObservation.created_at.asc())
        )
    ).scalars().all()


async def set_observation_confirmation(
    db: AsyncSession,
    *,
    session: InterviewSession,
    observation_id: str,
    confirm: bool,
) -> InterviewObservation:
    if session.status == "revoked" or session.revoked_at is not None:
        raise RuntimeError("session_revoked")
    observation = await db.get(InterviewObservation, observation_id)
    if not observation:
        raise PermissionError("observation_not_found")
    answer = await db.get(InterviewAnswer, observation.answer_id)
    question = await db.get(InterviewQuestion, answer.question_id) if answer else None
    if not question or str(question.session_id) != str(session.id):
        raise PermissionError("observation_not_in_session")
    if observation.candidate_confirmation_state != "pending":
        raise RuntimeError("observation_already_resolved")
    observation.candidate_confirmation_state = "confirmed" if confirm else "rejected"
    await db.flush()
    return observation


async def apply_confirmed_observation_to_claim(
    db: AsyncSession,
    *,
    session: InterviewSession,
    observation: InterviewObservation,
    actor_id: str,
) -> ResumeClaim | None:
    """Write back only after user confirms; practice mode never writes Claims."""
    if session.mode == "practice":
        raise PermissionError("practice_isolated")
    if observation.candidate_confirmation_state != "confirmed":
        raise PermissionError("observation_unconfirmed")
    if not (session.consent_snapshot or {}).get("resume_write"):
        raise PermissionError("resume_write_not_consented")
    if session.status == "revoked" or session.revoked_at is not None:
        raise RuntimeError("session_revoked")

    claim_id = observation.claim_id or session.claim_id
    claim = None
    if claim_id:
        claim = await db.get(ResumeClaim, claim_id)
        if not claim or str(claim.user_id) != str(session.user_id):
            raise PermissionError("claim_not_owned")
        if claim.workflow_state == "withdrawn":
            raise PermissionError("claim_withdrawn")
    elif session.mode in {"vault_builder", "target_gap"}:
        resume_id = session.resume_id
        if not resume_id:
            raise PermissionError("resume_required_for_writeback")
        resume = await db.get(Resume, resume_id)
        if not resume or str(resume.user_id) != str(session.user_id):
            raise PermissionError("resume_not_owned")
        from .models_db import CareerExperience

        experience = CareerExperience(
            id=str(uuid.uuid4()),
            user_id=str(session.user_id),
            experience_type="other",
            title="面试澄清写入",
            description=observation.text,
            date_precision="unknown",
            source_kind="interview",
            source_ref=f"interview_session:{session.id}:observation:{observation.id}",
            workflow_state="active",
        )
        db.add(experience)
        await db.flush()
        claim = ResumeClaim(
            id=str(uuid.uuid4()),
            resume_id=str(resume.id),
            user_id=str(session.user_id),
            career_experience_id=str(experience.id),
            source_key=f"interview_obs:{observation.id}",
            section="interview",
            field_path=f"interview_sessions.{session.id}.observations.{observation.id}",
            claim_type="action",
            original_text=observation.text,
            current_text=observation.text,
            origin_kind="interview",
            source_object_type="interview_observation",
            source_object_id=str(observation.id),
            confirmation_state="user_confirmed",
            confirmed_at=now_utc(),
            evidence_state="supported_by_user_evidence",
            workflow_state="open",
        )
        db.add(claim)
        await db.flush()
        observation.claim_id = str(claim.id)
    else:
        return None

    db.add(
        ClaimEvent(
            id=str(uuid.uuid4()),
            claim_id=str(claim.id),
            event_type="interview_observation_confirmed",
            actor_id=str(actor_id),
            payload={
                "observation_id": str(observation.id),
                "session_id": str(session.id),
                "text": observation.text,
                "source_start": observation.source_start,
                "source_end": observation.source_end,
                "mode": session.mode,
            },
        )
    )
    claim.evidence_state = "supported_by_user_evidence"
    claim.updated_at = now_utc()
    await db.flush()
    return claim


async def complete_session(db: AsyncSession, session: InterviewSession) -> InterviewSession:
    if session.status == "revoked":
        raise RuntimeError("session_revoked")
    session.status = "completed"
    session.completed_at = now_utc()
    await db.flush()
    return session


async def revoke_session(db: AsyncSession, session: InterviewSession, *, actor_id: str | None = None) -> InterviewSession:
    """Revoke purpose consent and stop further use of session outputs."""
    session.status = "revoked"
    session.revoked_at = now_utc()
    # Clear purpose authorization at session level.
    session.consent_snapshot = _consent_defaults({})

    observations = await list_observations_for_session(db, str(session.id))
    answer_ids: set[str] = set()
    claim_ids: set[str] = set()
    for observation in observations:
        answer_ids.add(str(observation.answer_id))
        if observation.candidate_confirmation_state == "pending":
            observation.candidate_confirmation_state = "rejected"
        if observation.claim_id:
            claim_ids.add(str(observation.claim_id))

    if answer_ids:
        answers = (
            await db.execute(select(InterviewAnswer).where(InterviewAnswer.id.in_(list(answer_ids))))
        ).scalars().all()
        for answer in answers:
            answer.allowed_uses = _consent_defaults({})
            answer.share_with_employer = False

    # Withdraw claims created/updated from this session and append revoke events.
    for claim_id in claim_ids:
        claim = await db.get(ResumeClaim, claim_id)
        if not claim or str(claim.user_id) != str(session.user_id):
            continue
        linked = (
            await db.execute(
                select(ClaimEvent).where(
                    ClaimEvent.claim_id == claim_id,
                    ClaimEvent.event_type == "interview_observation_confirmed",
                )
            )
        ).scalars().all()
        from_this_session = [
            event
            for event in linked
            if str((event.payload or {}).get("session_id") or "") == str(session.id)
        ]
        if not from_this_session:
            continue
        if claim.workflow_state != "withdrawn" and (
            claim.source_object_type == "interview_observation"
            or claim.origin_kind == "interview"
        ):
            claim.workflow_state = "withdrawn"
            claim.confirmation_state = "withdrawn"
        db.add(
            ClaimEvent(
                id=str(uuid.uuid4()),
                claim_id=str(claim.id),
                event_type="interview_session_revoked",
                actor_id=str(actor_id) if actor_id else None,
                payload={
                    "session_id": str(session.id),
                    "revoked_at": session.revoked_at.isoformat() if session.revoked_at else None,
                },
            )
        )

    await db.flush()
    return session


def serialize_question(row: InterviewQuestion) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "session_id": str(row.session_id),
        "sequence_no": row.sequence_no,
        "question_goal": row.question_goal,
        "claim_id": str(row.claim_id) if row.claim_id else None,
        "requirement_id": row.requirement_id,
        "competency_id": row.competency_id,
        "core_or_probe": row.core_or_probe,
        "question_text": row.question_text,
        "policy_version": row.policy_version,
        "generated_by": row.generated_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def serialize_answer(row: InterviewAnswer) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "question_id": str(row.question_id),
        "answer_text_snapshot": row.answer_text_snapshot,
        "user_declined": row.user_declined,
        "decline_reason": row.decline_reason,
        "allowed_uses": row.allowed_uses or {},
        "share_with_employer": row.share_with_employer,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def serialize_observation(row: InterviewObservation, *, answer_text: str | None = None) -> dict[str, Any]:
    payload = {
        "id": str(row.id),
        "answer_id": str(row.answer_id),
        "observation_type": row.observation_type,
        "text": row.text,
        "source_start": row.source_start,
        "source_end": row.source_end,
        "claim_id": str(row.claim_id) if row.claim_id else None,
        "candidate_confirmation_state": row.candidate_confirmation_state,
        "extractor_version": row.extractor_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if answer_text is not None:
        payload["source_excerpt"] = answer_text[row.source_start : row.source_end]
        payload["offset_valid"] = answer_text[row.source_start : row.source_end] == row.text
    return payload


def serialize_session(
    row: InterviewSession,
    *,
    questions: list[InterviewQuestion] | None = None,
    answered_count: int | None = None,
) -> dict[str, Any]:
    total = len(questions or [])
    return {
        "id": str(row.id),
        "mode": row.mode,
        "status": row.status,
        "job_id": str(row.job_id) if row.job_id else None,
        "resume_id": str(row.resume_id) if row.resume_id else None,
        "claim_id": str(row.claim_id) if row.claim_id else None,
        "consent_snapshot": row.consent_snapshot or {},
        "policy_version": row.policy_version,
        "ai_enabled": row.ai_enabled,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "progress": {
            "question_total": total,
            "answered_count": answered_count if answered_count is not None else 0,
        },
        "questions": [serialize_question(item) for item in (questions or [])],
    }


async def session_progress(db: AsyncSession, session_id: str) -> tuple[list[InterviewQuestion], int]:
    questions = await list_questions(db, session_id)
    if not questions:
        return [], 0
    answered = int(
        await db.scalar(
            select(func.count())
            .select_from(InterviewAnswer)
            .where(InterviewAnswer.question_id.in_([str(q.id) for q in questions]))
        )
        or 0
    )
    return questions, answered


async def build_session_report(
    db: AsyncSession,
    session: InterviewSession,
) -> dict[str, Any]:
    """Build candidate-facing, deterministic feedback from saved interview data."""

    questions = await list_questions(db, str(session.id))
    answers = (
        await db.execute(
            select(InterviewAnswer).where(
                InterviewAnswer.question_id.in_([str(row.id) for row in questions] or ["__none__"])
            )
        )
    ).scalars().all()
    answer_by_question = {str(row.question_id): row for row in answers}
    observations = await list_observations_for_session(db, str(session.id))
    usable = [
        row for row in observations
        if row.candidate_confirmation_state != "rejected"
    ]
    observation_types = {row.observation_type for row in usable}
    answered = [row for row in answers if not row.user_declined and row.answer_text_snapshot.strip()]
    declined = [row for row in answers if row.user_declined]
    answer_corpus = "\n".join(row.answer_text_snapshot for row in answered)
    resume = await db.get(Resume, str(session.resume_id)) if session.resume_id else None
    job = await db.get(JobDescription, str(session.job_id)) if session.job_id else None
    context = guidance_context(
        resume_json=resume.parsed_json if resume else None,
        job_json=job.parsed_json if job else None,
        job_title=job.title if job else None,
        corpus=answer_corpus,
    )
    anchor_name = context["anchor_experience"]["title"]
    target_role = context["target_role"]

    prior_session_ids = list(
        (
            await db.execute(
                select(InterviewSession.id)
                .where(
                    InterviewSession.user_id == str(session.user_id),
                    InterviewSession.id != str(session.id),
                    InterviewSession.status == "completed",
                )
                .order_by(InterviewSession.created_at.desc())
                .limit(5)
            )
        ).scalars().all()
    )
    prior_types: dict[str, set[str]] = {str(value): set() for value in prior_session_ids}
    if prior_session_ids:
        prior_rows = (
            await db.execute(
                select(InterviewQuestion.session_id, InterviewObservation.observation_type)
                .join(InterviewAnswer, InterviewAnswer.question_id == InterviewQuestion.id)
                .join(InterviewObservation, InterviewObservation.answer_id == InterviewAnswer.id)
                .where(InterviewQuestion.session_id.in_([str(value) for value in prior_session_ids]))
            )
        ).all()
        for prior_session_id, observation_type in prior_rows:
            prior_types.setdefault(str(prior_session_id), set()).add(str(observation_type))
    recurring_gap_types = {
        kind
        for kind in ("candidate_action", "result", "metric", "reflection")
        if len(prior_types) >= 2
        and sum(kind not in values for values in prior_types.values()) >= 2
    }

    strength_types = {
        "candidate_action": (
            "个人贡献表达清楚",
            "这让面试官能够区分你的实际贡献与团队整体成果。",
            "继续保留“我选择 / 我负责 / 我推动”的动作，并补一句协作边界。",
        ),
        "method": (
            "方法与技术路径具体",
            f"你不是只说完成了任务，而是在解释「{anchor_name}」中如何解决问题。",
            "下一次再补充“为什么选这个方法，而不是另一个方案”。",
        ),
        "result": (
            "能够落到结果或产出",
            "回答已经从工作过程走向影响，有利于判断你的执行闭环。",
            "保留结果句，并补充受益对象、验证方式或使用场景。",
        ),
        "metric": (
            "量化口径具有可核对性",
            "真实的数量、周期或前后变化能显著提高案例的信息密度。",
            "数字后面继续带上统计范围、时间边界和数据来源。",
        ),
        "reflection": (
            "具备复盘和迁移意识",
            f"这比只复述任务更能体现你面向{target_role or '下一段工作'}持续改进的能力。",
            "继续说明下一次会保留什么、改变什么，以及原因。",
        ),
    }
    strengths = [
        {
            "title": content[0],
            "evidence": next(
                (row.text for row in usable if row.observation_type == kind),
                "",
            ),
            "why_it_matters": content[1],
            "keep_doing": content[2],
            "source": "本次回答",
        }
        for kind, content in strength_types.items()
        if kind in observation_types
    ][:4]
    if not strengths and answered:
        strengths.append({
            "title": "完成了有效回答",
            "evidence": "本次回答已形成可回看的会话记录。",
            "why_it_matters": "这为后续逐次训练和比较提供了起点。",
            "keep_doing": f"下一次继续使用「{anchor_name}」作为练习案例，并增加一个可核对细节。",
            "source": "本次回答",
        })

    gaps: list[dict[str, str]] = []
    gap_types: list[str] = []
    if "candidate_action" not in observation_types:
        gap_types.append("candidate_action")
        gaps.append({
            "title": "个人贡献不够清楚",
            "detail": f"你提到了「{anchor_name}」，但回答中还没有稳定地区分“我做了什么”和“团队做了什么”。",
            "impact": "招聘方可能认可项目本身，却无法判断你的责任边界和独立解决问题能力。",
        })
    if not {"result", "metric"} & observation_types:
        gap_types.extend(["result", "metric"])
        gaps.append({
            "title": "结果证据偏弱",
            "detail": f"「{anchor_name}」已有行动描述，但缺少交付物、影响范围、效率或前后变化。",
            "impact": "面试官难以判断这段经历的完成质量和对目标岗位的实际价值。",
        })
    if "reflection" not in observation_types:
        gap_types.append("reflection")
        gaps.append({
            "title": "复盘深度不足",
            "detail": f"当前还没有看到你在「{anchor_name}」中的关键取舍、局限和下一次改法。",
            "impact": f"这会削弱你对{target_role or '复杂任务'}的学习速度与可迁移能力展示。",
        })
    if declined or len(answered) < len(questions):
        gap_types.append("completeness")
        gaps.append({
            "title": "回答完整度不足",
            "detail": f"{len(questions)} 道题中完成 {len(answered)} 道有效回答。",
            "impact": "部分能力没有获得被观察和反馈的机会。",
        })

    coaching = build_interview_action_plan(
        gap_types=gap_types,
        resume_json=resume.parsed_json if resume else None,
        job_json=job.parsed_json if job else None,
        job_title=job.title if job else None,
        answer_corpus=answer_corpus,
        recurring_gap_types=recurring_gap_types,
    )
    improvements = [
        f"{item['title']}（{item['estimated_effort']}）：{item['practice_prompt']}"
        for item in coaching["actions"]
    ]

    scores = {
        "回答完整度": round(100 * len(answered) / max(len(questions), 1)),
        "个人贡献清晰度": 85 if "candidate_action" in observation_types else 35,
        "结果证据": 90 if "metric" in observation_types else (70 if "result" in observation_types else 30),
        "复盘深度": 85 if "reflection" in observation_types else 35,
    }
    transcript = []
    for question in questions:
        answer = answer_by_question.get(str(question.id))
        transcript.append({
            "question_id": str(question.id),
            "sequence_no": question.sequence_no,
            "question_goal": question.question_goal,
            "question_text": question.question_text,
            "answer_text": answer.answer_text_snapshot if answer and not answer.user_declined else None,
            "declined": bool(answer.user_declined) if answer else False,
            "decline_reason": answer.decline_reason if answer else None,
        })

    return {
        "status": session.status,
        "summary": (
            f"本次共 {len(questions)} 道题，完成 {len(answered)} 道有效回答；"
            f"识别到 {len(usable)} 条可回看的回答要点。"
        ),
        "strengths": strengths,
        "gaps": gaps[:4],
        "improvements": improvements[:4],
        "personalized_coaching": coaching,
        "recurring_patterns": [
            {
                "type": kind,
                "label": {
                    "candidate_action": "个人贡献表达",
                    "result": "结果闭环",
                    "metric": "量化口径",
                    "reflection": "复盘深度",
                }[kind],
                "evidence": f"最近 {len(prior_types)} 次已完成面试中至少 2 次未观察到该信号。",
            }
            for kind in sorted(recurring_gap_types)
        ],
        "scores": scores,
        "transcript": transcript,
        "disclaimer": (
            "反馈结合本次回答、你选择的简历与目标岗位（如有）；"
            "只评价当前可观察到的表达和证据，不代表事实认证、能力定论或录用判断。"
        ),
        "coaching_method": "任务标准 → 当前证据 → 具体差距 → 刻意练习 → 达标检查",
    }
