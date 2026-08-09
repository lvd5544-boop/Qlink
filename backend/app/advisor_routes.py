"""PR14 target-role profile and grounded advisor APIs."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .advisor import (
    answer_advisor,
    confirm_profile,
    get_or_create_profile,
    serialize_profile,
)
from .api_idempotency import idempotent_write
from .auth import get_current_user
from .database import get_db
from .job_parser import parse_job_rules_only
from .models_db import AdvisorMessage, JobDescription, Resume, TargetRoleProfileSnapshot, User
from .security import candidate_can_access_job, require_candidate
from .target_job_optimization import generate_diagnostic, serialize_diagnostic

router = APIRouter(prefix="/advisor", tags=["Job Advisor"])


class TargetJobImportBody(BaseModel):
    job_id: str | None = None
    title: str | None = Field(None, max_length=255)
    description_text: str | None = Field(None, max_length=100_000)


class AdvisorDiagnosticBody(BaseModel):
    resume_id: str


class AdvisorMessageBody(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    resume_id: str | None = None


class RequirementDecisionBody(BaseModel):
    requirement_id: str = Field(min_length=1, max_length=64)
    classification: Literal["hard", "preferred", "context"]


class ConfirmTargetJobProfileBody(BaseModel):
    requirements: list[RequirementDecisionBody] | None = Field(
        default=None,
        max_length=100,
    )


async def _job_or_404(
    db: AsyncSession,
    job_id: str,
    user: User | None = None,
) -> JobDescription:
    job = await db.get(JobDescription, str(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")
    if user is None and (job.parsed_json or {}).get("advisor_private"):
        raise HTTPException(status_code=404, detail="岗位不存在")
    if user is not None and not candidate_can_access_job(job, str(user.id)):
        raise HTTPException(status_code=404, detail="岗位不存在")
    return job


async def _current_profile(
    db: AsyncSession,
    job: JobDescription,
    user: User,
) -> TargetRoleProfileSnapshot:
    return await get_or_create_profile(
        db,
        job,
        actor_id=str(user.id),
    )


@router.post("/target-jobs/import")
async def import_target_job(
    body: TargetJobImportBody,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    if not body.job_id and not body.description_text:
        raise HTTPException(status_code=422, detail="请选择现有岗位或提供完整 JD")
    user_id = str(current_user.id)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="pr14.target_job.import",
        idempotency_key=idempotency_key,
        request_payload=body.model_dump(),
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        if body.job_id:
            job = await _job_or_404(db, body.job_id, current_user)
        else:
            parsed = parse_job_rules_only(body.description_text or "")
            parsed_json = parsed.model_dump()
            parsed_json.update(
                {
                    "title": body.title or parsed.title or "自定义目标岗位",
                    "source_name": "候选人导入 JD",
                    "advisor_imported_by": user_id,
                    "advisor_private": True,
                }
            )
            job = JobDescription(
                id=str(uuid.uuid4()),
                employer_id=None,
                title=parsed_json["title"],
                raw_text=body.description_text,
                parsed_json=parsed_json,
            )
            db.add(job)
            await db.flush()
        snapshot = await _current_profile(db, job, current_user)
        payload = await serialize_profile(db, snapshot, job)
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.get("/jobs/{job_id}/profile")
async def get_target_job_profile(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _job_or_404(db, job_id, current_user)
    snapshot = await _current_profile(db, job, current_user)
    return await serialize_profile(db, snapshot, job)


@router.post("/jobs/{job_id}/profile/confirm")
async def confirm_target_job_profile(
    job_id: str,
    body: ConfirmTargetJobProfileBody | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    job = await _job_or_404(db, job_id, current_user)
    if current_user.role != "employer" or str(job.employer_id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="岗位不存在或无权确认")
    snapshot = await _current_profile(db, job, current_user)
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope=f"pr14.profile.{snapshot.id}.confirm",
        idempotency_key=idempotency_key,
        request_payload={
            "job_id": job_id,
            "snapshot_id": str(snapshot.id),
            "requirements": body.model_dump()["requirements"] if body else None,
        },
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        decisions = None
        if body and body.requirements is not None:
            decisions = {item.requirement_id: item.classification for item in body.requirements}
            if len(decisions) != len(body.requirements):
                raise HTTPException(status_code=422, detail="岗位要求不能重复")
        try:
            await confirm_profile(
                db,
                snapshot,
                employer_id=str(current_user.id),
                requirement_decisions=decisions,
            )
        except ValueError as exc:
            mapping = {
                "requirement_decisions_incomplete": "请确认全部岗位要求的优先级",
                "invalid_requirement_classification": "岗位要求优先级无效",
            }
            raise HTTPException(
                status_code=422,
                detail=mapping.get(str(exc), "岗位要求确认失败"),
            ) from exc
        parsed = dict(job.parsed_json or {})
        parsed["_publication_status"] = "published"
        job.parsed_json = parsed
        payload = await serialize_profile(db, snapshot, job)
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.get("/jobs/{job_id}/source-trace")
async def get_profile_source_trace(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _job_or_404(db, job_id, current_user)
    snapshot = await _current_profile(db, job, current_user)
    return {
        "job_id": str(job.id),
        "profile_snapshot_id": str(snapshot.id),
        "snapshot_hash": snapshot.snapshot_hash,
        "sources": snapshot.source_manifest or [],
        "reproducible": True,
    }


@router.post("/jobs/{job_id}/diagnostics")
async def create_advisor_diagnostic(
    job_id: str,
    body: AdvisorDiagnosticBody,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    job = await _job_or_404(db, job_id, current_user)
    snapshot = await _current_profile(db, job, current_user)
    user_id = str(current_user.id)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope=f"pr14.advisor.{job_id}.diagnostics",
        idempotency_key=idempotency_key,
        request_payload=body.model_dump(),
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        diagnostic_id = await generate_diagnostic(
            db,
            user_id=user_id,
            resume_id=body.resume_id,
            job_id=str(job.id),
        )
        payload = await serialize_diagnostic(
            db,
            user_id=user_id,
            job_id=str(job.id),
            diagnostic_id=diagnostic_id,
        )
        payload["profile_snapshot_id"] = str(snapshot.id)
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.get("/jobs/{job_id}/diagnostics/{diagnostic_id}")
async def get_advisor_diagnostic(
    job_id: str,
    diagnostic_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await serialize_diagnostic(
            db,
            user_id=str(current_user.id),
            job_id=job_id,
            diagnostic_id=diagnostic_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="诊断不存在或无权访问") from exc


@router.post("/jobs/{job_id}/chat/messages")
async def post_advisor_message(
    job_id: str,
    body: AdvisorMessageBody,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    job = await _job_or_404(db, job_id, current_user)
    snapshot = await _current_profile(db, job, current_user)
    resume = None
    if body.resume_id:
        resume = await db.get(Resume, body.resume_id)
        if not resume or str(resume.user_id) != str(current_user.id):
            raise HTTPException(status_code=404, detail="简历不存在或无权访问")
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope=f"pr14.advisor.{job_id}.chat",
        idempotency_key=idempotency_key,
        request_payload=body.model_dump(),
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        payload = await answer_advisor(
            db,
            user_id=str(current_user.id),
            job=job,
            snapshot=snapshot,
            message=body.message.strip(),
            resume=resume,
        )
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.get("/jobs/{job_id}/chat/messages")
async def list_advisor_messages(
    job_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    await _job_or_404(db, job_id, current_user)
    rows = (
        (
            await db.execute(
                select(AdvisorMessage)
                .where(
                    AdvisorMessage.user_id == str(current_user.id),
                    AdvisorMessage.job_id == str(job_id),
                )
                .order_by(AdvisorMessage.created_at)
            )
        )
        .scalars()
        .all()
    )
    return {
        "messages": [
            {
                "id": str(row.id),
                "role": row.role,
                "content": row.content,
                "statements": row.statements or [],
                "response_trace": row.response_trace or {},
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }
