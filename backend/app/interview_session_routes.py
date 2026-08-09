"""REST API for PR12 structured interview sessions."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .api_idempotency import idempotent_write
from .database import get_db
from .interview_sessions import (
    apply_confirmed_observation_to_claim,
    build_session_report,
    complete_session,
    create_session,
    list_observations_for_session,
    next_question,
    owned_session,
    revoke_session,
    serialize_answer,
    serialize_observation,
    serialize_question,
    serialize_session,
    session_progress,
    set_observation_confirmation,
    submit_answer,
)
from .models_db import (
    InterviewAnswer,
    InterviewObservation,
    InterviewQuestion,
    InterviewSession,
    User,
)
from .security import require_candidate

router = APIRouter(tags=["结构化 AI 面试官"])


class ConsentBody(BaseModel):
    resume_write: bool = False
    job_recommendation: bool = False
    employer_share: bool = False
    model_improvement: bool = False


class CreateSessionBody(BaseModel):
    mode: str
    job_id: Optional[str] = None
    resume_id: Optional[str] = None
    claim_id: Optional[str] = None
    consent_snapshot: ConsentBody = Field(default_factory=ConsentBody)
    ai_enabled: bool = True


class AnswerBody(BaseModel):
    question_id: str
    answer_text: Optional[str] = None
    user_declined: bool = False
    decline_reason: Optional[str] = None
    allowed_uses: Optional[ConsentBody] = None
    share_with_employer: bool = False


def _map_error(exc: Exception) -> HTTPException:
    message = str(exc)
    mapping = {
        "invalid_mode": (422, "面试模式无效"),
        "claim_required": (422, "Claim 澄清模式必须指定 claim_id"),
        "job_required": (422, "目标岗位模式必须指定 job_id"),
        "job_requirements_empty": (422, "目标岗位缺少可追问的技能要求"),
        "claim_not_owned": (404, "主张不存在或无权访问"),
        "resume_not_owned": (404, "简历不存在或无权访问"),
        "job_not_found": (404, "岗位不存在"),
        "job_not_owned": (404, "岗位不存在或无权访问"),
        "session_not_active": (409, "会话已结束"),
        "session_revoked": (409, "会话已撤回，不能继续使用"),
        "question_not_in_session": (404, "问题不存在或不属于该会话"),
        "answer_already_exists": (409, "该问题已回答"),
        "answer_required": (422, "请填写回答，或选择拒答"),
        "invalid_decline_reason": (422, "拒答原因无效"),
        "observation_not_found": (404, "观察结果不存在"),
        "observation_not_in_session": (404, "观察结果不存在或不属于该会话"),
        "observation_already_resolved": (409, "观察结果已确认或已拒绝"),
        "practice_isolated": (409, "模拟面试不会写入 Claim 或简历"),
        "observation_unconfirmed": (409, "未确认的观察结果不能写简历"),
        "resume_write_not_consented": (403, "未授权简历写回用途"),
        "resume_required_for_writeback": (422, "写入职业记忆需要关联简历"),
        "claim_withdrawn": (409, "主张已撤回，不能继续使用"),
        "sensitive_or_discriminatory_question": (422, "问题包含敏感或歧视性内容，已拦截"),
    }
    status, detail = mapping.get(message, (400, message))
    return HTTPException(status_code=status, detail=detail)


async def _session_for_observation(db: AsyncSession, observation_id: str, user_id: str):
    observation = await db.get(InterviewObservation, observation_id)
    if not observation:
        return None, None
    answer = await db.get(InterviewAnswer, observation.answer_id)
    question = await db.get(InterviewQuestion, answer.question_id) if answer else None
    if not question:
        return None, None
    session = await owned_session(db, str(question.session_id), user_id)
    return session, observation


@router.post("/interview-sessions")
async def create_interview_session(
    body: CreateSessionBody,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope="interview.session.create",
        idempotency_key=idempotency_key,
        request_payload=body.model_dump(),
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        try:
            session = await create_session(
                db,
                user_id=str(current_user.id),
                mode=body.mode,
                job_id=body.job_id,
                resume_id=body.resume_id,
                claim_id=body.claim_id,
                consent_snapshot=body.consent_snapshot.model_dump(),
                ai_enabled=body.ai_enabled,
            )
            questions, answered = await session_progress(db, str(session.id))
            payload = {
                "session": serialize_session(session, questions=questions, answered_count=answered)
            }
            gate.set_response(200, payload)
            await db.commit()
            return payload
        except (ValueError, PermissionError, RuntimeError) as exc:
            raise _map_error(exc) from exc


@router.get("/interview-sessions")
async def list_interview_sessions(
    limit: int = 20,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    bounded_limit = max(1, min(limit, 50))
    rows = (
        (
            await db.execute(
                select(InterviewSession)
                .where(InterviewSession.user_id == str(current_user.id))
                .order_by(InterviewSession.created_at.desc())
                .limit(bounded_limit)
            )
        )
        .scalars()
        .all()
    )
    items = []
    for row in rows:
        questions, answered = await session_progress(db, str(row.id))
        payload = serialize_session(row, questions=questions, answered_count=answered)
        payload["report"] = await build_session_report(db, row)
        items.append(payload)
    return {"sessions": items}


@router.get("/interview-sessions/{session_id}")
async def get_interview_session(
    session_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    session = await owned_session(db, session_id, str(current_user.id))
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    questions, answered = await session_progress(db, session_id)
    return {
        "session": serialize_session(session, questions=questions, answered_count=answered),
        "report": await build_session_report(db, session),
    }


@router.post("/interview-sessions/{session_id}/next-question")
async def get_next_question(
    session_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope="interview.session.next_question",
        idempotency_key=idempotency_key,
        request_payload={"session_id": session_id},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        session = await owned_session(db, session_id, str(current_user.id))
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在或无权访问")
        try:
            question = await next_question(db, session)
            payload = (
                {"question": None, "done": True}
                if question is None
                else {"question": serialize_question(question), "done": False}
            )
            gate.set_response(200, payload)
            await db.commit()
            return payload
        except RuntimeError as exc:
            raise _map_error(exc) from exc


@router.post("/interview-sessions/{session_id}/answers")
async def post_answer(
    session_id: str,
    body: AnswerBody,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope="interview.session.answer",
        idempotency_key=idempotency_key,
        request_payload={"session_id": session_id, **body.model_dump()},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        session = await owned_session(db, session_id, str(current_user.id))
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在或无权访问")
        try:
            answer, observations = await submit_answer(
                db,
                session=session,
                question_id=body.question_id,
                answer_text=body.answer_text,
                user_declined=body.user_declined,
                decline_reason=body.decline_reason,
                allowed_uses=body.allowed_uses.model_dump() if body.allowed_uses else None,
                share_with_employer=body.share_with_employer,
            )
            payload = {
                "answer": serialize_answer(answer),
                "observations": [
                    serialize_observation(row, answer_text=answer.answer_text_snapshot)
                    for row in observations
                ],
            }
            gate.set_response(200, payload)
            await db.commit()
            return payload
        except (ValueError, PermissionError, RuntimeError) as exc:
            raise _map_error(exc) from exc


@router.get("/interview-sessions/{session_id}/observations")
async def get_observations(
    session_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    session = await owned_session(db, session_id, str(current_user.id))
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    rows = await list_observations_for_session(db, session_id)
    payloads = []
    for row in rows:
        answer = await db.get(InterviewAnswer, row.answer_id)
        payloads.append(
            serialize_observation(
                row,
                answer_text=answer.answer_text_snapshot if answer else None,
            )
        )
    return {"observations": payloads}


@router.post("/interview-observations/{observation_id}/confirm")
async def confirm_observation(
    observation_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope="interview.observation.confirm",
        idempotency_key=idempotency_key,
        request_payload={"observation_id": observation_id, "action": "confirm"},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        session, _ = await _session_for_observation(db, observation_id, str(current_user.id))
        if not session:
            raise HTTPException(status_code=404, detail="观察结果不存在或无权访问")
        try:
            observation = await set_observation_confirmation(
                db, session=session, observation_id=observation_id, confirm=True
            )
            claim = None
            write_error = None
            try:
                claim = await apply_confirmed_observation_to_claim(
                    db,
                    session=session,
                    observation=observation,
                    actor_id=str(current_user.id),
                )
            except PermissionError as exc:
                write_error = str(exc)
            payload = {
                "observation": serialize_observation(observation),
                "claim_id": str(claim.id) if claim else None,
                "writeback": "applied" if claim else ("blocked" if write_error else "skipped"),
                "writeback_reason": write_error,
            }
            gate.set_response(200, payload)
            await db.commit()
            return payload
        except (PermissionError, RuntimeError) as exc:
            raise _map_error(exc) from exc


@router.post("/interview-observations/{observation_id}/reject")
async def reject_observation(
    observation_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope="interview.observation.reject",
        idempotency_key=idempotency_key,
        request_payload={"observation_id": observation_id, "action": "reject"},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        session, _ = await _session_for_observation(db, observation_id, str(current_user.id))
        if not session:
            raise HTTPException(status_code=404, detail="观察结果不存在或无权访问")
        try:
            observation = await set_observation_confirmation(
                db, session=session, observation_id=observation_id, confirm=False
            )
            payload = {"observation": serialize_observation(observation)}
            gate.set_response(200, payload)
            await db.commit()
            return payload
        except (PermissionError, RuntimeError) as exc:
            raise _map_error(exc) from exc


@router.post("/interview-sessions/{session_id}/complete")
async def complete_interview_session(
    session_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope="interview.session.complete",
        idempotency_key=idempotency_key,
        request_payload={"session_id": session_id},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        session = await owned_session(db, session_id, str(current_user.id))
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在或无权访问")
        try:
            session = await complete_session(db, session)
            questions, answered = await session_progress(db, session_id)
            payload = {
                "session": serialize_session(session, questions=questions, answered_count=answered),
                "report": await build_session_report(db, session),
            }
            gate.set_response(200, payload)
            await db.commit()
            return payload
        except RuntimeError as exc:
            raise _map_error(exc) from exc


@router.post("/interview-sessions/{session_id}/revoke")
async def revoke_interview_session(
    session_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope="interview.session.revoke",
        idempotency_key=idempotency_key,
        request_payload={"session_id": session_id},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        session = await owned_session(db, session_id, str(current_user.id))
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在或无权访问")
        session = await revoke_session(db, session, actor_id=str(current_user.id))
        questions, answered = await session_progress(db, session_id)
        payload = {
            "session": serialize_session(session, questions=questions, answered_count=answered)
        }
        gate.set_response(200, payload)
        await db.commit()
        return payload
