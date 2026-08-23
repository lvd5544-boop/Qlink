"""Candidate-owned pilot consent and feedback APIs."""

from __future__ import annotations

from datetime import datetime, timezone
import os
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .api_idempotency import idempotent_write
from .database import get_db
from .models_db import PilotConsent, PilotFeedback, PilotParticipant, User
from .security import require_candidate

router = APIRouter(prefix="/pilot", tags=["pilot"])

CONSENT_VERSION = os.getenv("PILOT_CONSENT_VERSION", "pilot-v1")
NOTICE_SNAPSHOT = {
    "purpose": "product_usability_research",
    "no_automatic_submission": True,
    "candidate_confirms_inferred_facts": True,
    "model_improvement_is_optional": True,
}


class PilotConsentBody(BaseModel):
    product_research: bool
    aggregate_metrics: bool = False
    model_improvement: bool = False


class PilotFeedbackBody(BaseModel):
    category: str = Field(pattern="^(usability|trust|recommendation|bug|other)$")
    rating: int = Field(ge=1, le=5)
    context: str = Field(default="pilot_hub", min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=2000)
    allow_follow_up: bool = False


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def _participant(db: AsyncSession, user_id: str) -> PilotParticipant | None:
    return (
        await db.execute(select(PilotParticipant).where(PilotParticipant.user_id == str(user_id)))
    ).scalar_one_or_none()


async def _latest_consent(db: AsyncSession, participant_id: str) -> PilotConsent | None:
    return (
        await db.execute(
            select(PilotConsent)
            .where(PilotConsent.participant_id == participant_id)
            .order_by(PilotConsent.created_at.desc(), PilotConsent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _state(participant: PilotParticipant | None, consent: PilotConsent | None) -> dict:
    return {
        "enrolled": bool(participant and participant.status == "active"),
        "status": participant.status if participant else "not_enrolled",
        "participant_code": participant.participant_code if participant else None,
        "consent_version": consent.consent_version if consent else CONSENT_VERSION,
        "product_research": bool(consent.product_research) if consent else False,
        "aggregate_metrics": bool(consent.aggregate_metrics) if consent else False,
        "model_improvement": bool(consent.model_improvement) if consent else False,
        "accepted_at": _iso(consent.created_at)
        if consent and consent.action != "withdrawn"
        else None,
        "withdrawn_at": _iso(participant.withdrawn_at) if participant else None,
    }


@router.get("/me")
async def get_pilot_state(
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    participant = await _participant(db, str(current_user.id))
    consent = await _latest_consent(db, participant.id) if participant else None
    return _state(participant, consent)


@router.post("/consent")
async def accept_or_update_consent(
    body: PilotConsentBody,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    if not body.product_research:
        raise HTTPException(status_code=422, detail="参加 pilot 必须明确同意产品试用研究")
    payload = body.model_dump()
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope="pilot-consent",
        idempotency_key=idempotency_key,
        request_payload=payload,
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        participant = await _participant(db, str(current_user.id))
        action = "updated"
        if participant is None:
            participant = PilotParticipant(
                id=str(uuid.uuid4()),
                user_id=str(current_user.id),
                participant_code=str(uuid.uuid4()),
                status="active",
            )
            db.add(participant)
            # There is intentionally no ORM relationship between the
            # de-identified pilot identity and consent history. Flush the
            # parent explicitly so SQLite and PostgreSQL observe the FK order.
            await db.flush()
            action = "accepted"
        elif participant.status == "withdrawn":
            participant.status = "active"
            participant.withdrawn_at = None
            action = "accepted"
        consent_record = PilotConsent(
            id=str(uuid.uuid4()),
            participant_id=participant.id,
            consent_version=CONSENT_VERSION,
            action=action,
            product_research=True,
            aggregate_metrics=body.aggregate_metrics,
            model_improvement=body.model_improvement,
            notice_snapshot=NOTICE_SNAPSHOT,
        )
        db.add(consent_record)
        await db.flush()
        response = _state(participant, consent_record)
        gate.set_response(200, response)
        await db.commit()
        return response


@router.post("/withdraw")
async def withdraw_from_pilot(
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope="pilot-withdraw",
        idempotency_key=idempotency_key,
        request_payload={"action": "withdraw", "version": CONSENT_VERSION},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        participant = await _participant(db, str(current_user.id))
        if participant is None or participant.status == "withdrawn":
            response = _state(
                participant, await _latest_consent(db, participant.id) if participant else None
            )
            gate.set_response(200, response)
            await db.commit()
            return response
        previous = await _latest_consent(db, participant.id)
        participant.status = "withdrawn"
        participant.withdrawn_at = datetime.now(timezone.utc)
        consent_record = PilotConsent(
            id=str(uuid.uuid4()),
            participant_id=participant.id,
            consent_version=CONSENT_VERSION,
            action="withdrawn",
            product_research=False,
            aggregate_metrics=False,
            model_improvement=False,
            notice_snapshot={
                **NOTICE_SNAPSHOT,
                "previous_consent_version": previous.consent_version if previous else None,
            },
        )
        db.add(consent_record)
        await db.flush()
        response = _state(participant, consent_record)
        gate.set_response(200, response)
        await db.commit()
        return response


@router.post("/feedback", status_code=201)
async def submit_pilot_feedback(
    body: PilotFeedbackBody,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    participant = await _participant(db, str(current_user.id))
    if participant is None or participant.status != "active":
        raise HTTPException(status_code=409, detail="请先同意参加 pilot，再提交试用反馈")
    payload = body.model_dump()
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope="pilot-feedback",
        idempotency_key=idempotency_key,
        request_payload=payload,
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        feedback = PilotFeedback(
            id=str(uuid.uuid4()),
            participant_id=participant.id,
            **payload,
        )
        db.add(feedback)
        response = {"status": "received", "feedback_id": feedback.id}
        gate.set_response(201, response)
        await db.commit()
        return response
