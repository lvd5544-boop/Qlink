"""User confirmation, purpose consent, and revocation for interview artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .application_events import event_bus
from .auth import get_current_user
from .database import get_db
from .models_db import (
    ApplicationMessage,
    InterviewResult,
    JobApplication,
    Resume,
    User,
)

router = APIRouter(prefix="/interviews", tags=["AI 面试数据"])


class InterviewAllowedUses(BaseModel):
    resume_write: bool = False
    job_recommendation: bool = False
    employer_share: bool = False
    model_improvement: bool = False


class ConfirmInterviewResultRequest(BaseModel):
    allowed_uses: InterviewAllowedUses
    resume_id: Optional[str] = None


def _result_payload(row: InterviewResult, *, include_transcript: bool) -> dict:
    payload = {
        "id": str(row.id),
        "mode": row.mode,
        "status": row.status,
        "resume_id": str(row.resume_id) if row.resume_id else None,
        "application_id": (str(row.application_id) if row.application_id else None),
        "extracted": row.extracted_json or {},
        "source_references": row.source_references or [],
        "requested_uses": {
            key: bool((row.requested_uses or {}).get(key))
            for key in (
                "resume_write",
                "job_recommendation",
                "employer_share",
                "model_improvement",
            )
        },
        "allowed_uses": {
            key: bool((row.allowed_uses or {}).get(key))
            for key in (
                "resume_write",
                "job_recommendation",
                "employer_share",
                "model_improvement",
            )
        },
        "confirmed_at": (row.confirmed_at.isoformat() if row.confirmed_at else None),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if include_transcript:
        payload["transcript"] = row.transcript or []
    return payload


@router.get("/results/mine")
async def list_my_interview_results(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    statement = select(InterviewResult).where(InterviewResult.user_id == str(current_user.id))
    if status:
        statement = statement.where(InterviewResult.status == status)
    rows = (
        (
            await db.execute(
                statement.order_by(
                    InterviewResult.created_at.desc(),
                    InterviewResult.id.desc(),
                ).limit(100)
            )
        )
        .scalars()
        .all()
    )
    return {"data": [_result_payload(row, include_transcript=False) for row in rows]}


@router.get("/results/{result_id}")
async def get_my_interview_result(
    result_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(InterviewResult, result_id)
    if not row or row.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="资源不存在或无权访问")
    return _result_payload(row, include_transcript=True)


def _merge_profile(
    parsed: dict,
    extracted: dict,
    *,
    result_id: str,
) -> tuple[dict, dict]:
    current = dict(parsed or {})
    before: dict = {}
    applied: dict = {}
    scalar_fields = (
        "expected_job_title",
        "expected_salary",
        "education",
        "hobbies",
        "location_preference",
    )
    for field in scalar_fields:
        value = extracted.get(field)
        if value in (None, "", []):
            continue
        before[field] = current.get(field)
        current[field] = value
        applied[field] = value

    work_summary = str(extracted.get("work_summary") or "").strip()
    if work_summary:
        before["summary"] = current.get("summary")
        current["summary"] = "\n".join(
            part for part in (str(current.get("summary") or "").strip(), work_summary) if part
        )
        applied["summary"] = current["summary"]

    new_skills = [
        str(item).strip() for item in (extracted.get("skills") or []) if str(item).strip()
    ]
    if new_skills:
        before["skills"] = current.get("skills")
        existing = list(current.get("skills") or [])
        names = {
            str(item.get("name") if isinstance(item, dict) else item).strip() for item in existing
        }
        for name in new_skills:
            if name not in names:
                existing.append({"name": name, "level": "intermediate"})
                names.add(name)
        current["skills"] = existing
        applied["skills"] = existing

    provenance = list(current.get("interview_provenance") or [])
    provenance.append(
        {
            "interview_result_id": result_id,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "fields": list(applied),
        }
    )
    current["interview_provenance"] = provenance
    return current, {"before": before, "applied": applied}


def _merge_claim_answers(
    parsed: dict,
    answers: list[dict],
    *,
    result_id: str,
) -> tuple[dict, dict]:
    current = dict(parsed or {})
    had_field = "claim_followup_answers" in current
    existing = list(current.get("claim_followup_answers") or [])
    before_count = len(existing)
    confirmed_at = datetime.now(timezone.utc).isoformat()
    for item in answers:
        existing.append(
            {
                **item,
                "interview_result_id": result_id,
                "confirmed_at": confirmed_at,
            }
        )
    current["claim_followup_answers"] = existing
    return current, {
        "before_count": before_count,
        "had_field": had_field,
    }


async def _share_with_employer(
    db: AsyncSession,
    *,
    row: InterviewResult,
) -> Optional[JobApplication]:
    if not row.application_id:
        raise HTTPException(
            status_code=409,
            detail={"error": "interview_application_required"},
        )
    application = await db.get(JobApplication, str(row.application_id))
    if not application or application.candidate_id != row.user_id:
        raise HTTPException(status_code=404, detail="资源不存在或无权访问")

    existing = (
        (
            await db.execute(
                select(ApplicationMessage).where(
                    ApplicationMessage.application_id == str(application.id),
                    ApplicationMessage.message_kind == "interview_summary",
                )
            )
        )
        .scalars()
        .all()
    )
    if any(
        (message.message_meta or {}).get("interview_result_id") == str(row.id)
        for message in existing
    ):
        return application

    extracted = row.extracted_json or {}
    if row.mode == "claim_followup":
        lines = [
            f"- {item.get('claim_text') or item.get('claim_id')}: {item.get('answer') or ''}"
            for item in (extracted.get("answers") or [])
        ]
        body = "\n".join(lines) or "候选人确认分享了一次 Claim 追问结果。"
    else:
        body = str(extracted.get("summary") or "").strip()
        if not body:
            body = "候选人确认分享了一次职业发现面试摘要。"

    db.add(
        ApplicationMessage(
            application_id=str(application.id),
            sender_id=row.user_id,
            body=f"[候选人确认分享的 AI 面试纪要]\n{body}",
            message_kind="interview_summary",
            message_meta={
                "interview_result_id": str(row.id),
                "mode": row.mode,
                "candidate_confirmed": True,
            },
        )
    )
    return application


@router.post("/results/{result_id}/confirm")
async def confirm_interview_result(
    result_id: str,
    body: ConfirmInterviewResultRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(InterviewResult)
            .where(
                InterviewResult.id == result_id,
                InterviewResult.user_id == str(current_user.id),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="资源不存在或无权访问")
    requested = body.allowed_uses.model_dump()
    if row.status == "revoked":
        raise HTTPException(
            status_code=409,
            detail={"error": "interview_result_revoked"},
        )
    if row.status == "confirmed":
        visible = {key: bool((row.allowed_uses or {}).get(key)) for key in requested}
        if visible != requested:
            raise HTTPException(
                status_code=409,
                detail={"error": "interview_result_already_confirmed"},
            )
        return _result_payload(row, include_transcript=False)

    internal: dict = {}
    if requested["resume_write"]:
        target_id = body.resume_id or row.resume_id
        if not target_id:
            raise HTTPException(
                status_code=409,
                detail={"error": "resume_required_for_writeback"},
            )
        resume = await db.get(Resume, str(target_id))
        if not resume or resume.user_id != str(current_user.id):
            raise HTTPException(status_code=404, detail="资源不存在或无权访问")
        if row.mode == "profile":
            updated, writeback = _merge_profile(
                resume.parsed_json or {},
                row.extracted_json or {},
                result_id=str(row.id),
            )
        else:
            updated, writeback = _merge_claim_answers(
                resume.parsed_json or {},
                list((row.extracted_json or {}).get("answers") or []),
                result_id=str(row.id),
            )
        resume.parsed_json = updated
        row.resume_id = str(resume.id)
        internal["_writeback"] = {
            "resume_id": str(resume.id),
            **writeback,
        }

    shared_application = None
    if requested["employer_share"]:
        shared_application = await _share_with_employer(db, row=row)

    row.allowed_uses = {**requested, **internal}
    row.status = "confirmed"
    row.confirmed_at = datetime.now(timezone.utc)
    await db.commit()

    if shared_application is not None:
        await event_bus.publish(
            application_id=str(shared_application.id),
            event_type="interview_summary",
            payload={
                "interview_result_id": str(row.id),
                "candidate_confirmed": True,
            },
            candidate_id=shared_application.candidate_id,
            employer_id=shared_application.employer_id,
        )
    return _result_payload(row, include_transcript=False)


def _revoke_resume_writeback(resume: Resume, row: InterviewResult) -> None:
    current = dict(resume.parsed_json or {})
    writeback = (row.allowed_uses or {}).get("_writeback") or {}
    if row.mode == "claim_followup":
        remaining = [
            item
            for item in (current.get("claim_followup_answers") or [])
            if item.get("interview_result_id") != str(row.id)
        ]
        if remaining or writeback.get("had_field"):
            current["claim_followup_answers"] = remaining
        else:
            current.pop("claim_followup_answers", None)
    else:
        before = writeback.get("before") or {}
        applied = writeback.get("applied") or {}
        for field, old_value in before.items():
            # Do not overwrite edits made after confirmation.
            if current.get(field) != applied.get(field):
                continue
            if old_value is None:
                current.pop(field, None)
            else:
                current[field] = old_value
        current["interview_provenance"] = [
            item
            for item in (current.get("interview_provenance") or [])
            if item.get("interview_result_id") != str(row.id)
        ]
    resume.parsed_json = current


@router.delete("/results/{result_id}")
async def revoke_interview_result(
    result_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            select(InterviewResult)
            .where(
                InterviewResult.id == result_id,
                InterviewResult.user_id == str(current_user.id),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="资源不存在或无权访问")
    if row.status == "revoked":
        return {"status": "revoked", "id": str(row.id)}

    writeback = (row.allowed_uses or {}).get("_writeback") or {}
    resume_id = writeback.get("resume_id")
    if resume_id:
        resume = await db.get(Resume, str(resume_id))
        if resume and resume.user_id == str(current_user.id):
            _revoke_resume_writeback(resume, row)

    if row.application_id:
        messages = (
            (
                await db.execute(
                    select(ApplicationMessage).where(
                        ApplicationMessage.application_id == str(row.application_id),
                        ApplicationMessage.message_kind == "interview_summary",
                    )
                )
            )
            .scalars()
            .all()
        )
        for message in messages:
            if (message.message_meta or {}).get("interview_result_id") == str(row.id):
                await db.delete(message)

    row.status = "revoked"
    row.allowed_uses = {
        "resume_write": False,
        "job_recommendation": False,
        "employer_share": False,
        "model_improvement": False,
    }
    row.requested_uses = {
        "resume_write": False,
        "job_recommendation": False,
        "employer_share": False,
        "model_improvement": False,
    }
    row.transcript = []
    row.extracted_json = {}
    row.source_references = []
    await db.commit()
    return {"status": "revoked", "id": str(row.id)}
