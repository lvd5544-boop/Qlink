"""Candidate-owned PR11 Career Passport and Evidence Vault APIs."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .api_idempotency import idempotent_write
from .auth import get_current_user
from .career_vault import (
    build_map,
    create_resume_version,
    now_utc,
    owned_claim,
    serialize_artifact,
    serialize_experience,
)
from .claim_passport import _event, serialize_claim, sync_resume_claims
from .database import get_db
from .models_db import (
    CareerExperience,
    ClaimEvidence,
    ClaimEvent,
    ClaimRevision,
    EvidenceArtifact,
    Resume,
    ResumeClaim,
    ResumeVersion,
    User,
)
from .object_storage import (
    evidence_object_key,
    get_object_storage,
    issue_download_token,
    maybe_s3_presign,
    verify_download_token,
)
from .safe_upload import save_upload_safely
from .virus_scan import scan_bytes

router = APIRouter(tags=["Career Passport", "Evidence Vault"])

EXPERIENCE_TYPES = {"work", "project", "education", "volunteer", "freelance", "award", "other"}
ARTIFACT_TYPES = {"document", "link", "code", "sample", "certificate", "image", "user_statement", "other"}
ALLOWED_USES = {"resume_assistance", "application_share", "model_improvement"}
RELATIONSHIPS = {"supports", "contradicts", "related"}
EVIDENCE_FILE_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md", ".py", ".ipynb", ".js", ".ts",
    ".java", ".go", ".rs", ".sql", ".csv",
}


def _candidate(user: User) -> str:
    if user.role != "candidate":
        raise HTTPException(status_code=403, detail="仅候选人可访问职业档案")
    return str(user.id)


class ExperienceBody(BaseModel):
    experience_type: str
    organization: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    start_date: date | None = None
    end_date: date | None = None
    date_precision: str = "unknown"
    description: str | None = Field(default=None, max_length=20000)
    source_kind: str = "manual"
    workflow_state: str = "active"


class ClaimCreate(BaseModel):
    resume_id: str
    text: str = Field(min_length=1, max_length=20000)
    claim_type: str = Field(default="statement", max_length=48)
    field_path: str = Field(default="career_experience", max_length=255)


class ClaimPatch(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=20000)
    career_experience_id: str | None = None
    sensitivity_level: str | None = None
    default_visibility: str | None = None


class ChatMessageBody(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    question_goal: str = Field(default="clarify", max_length=64)
    ai_enabled: bool = True


class ArtifactInit(BaseModel):
    artifact_type: str
    title: str = Field(min_length=1, max_length=255)
    source_url: HttpUrl | None = None
    issuer: str | None = Field(default=None, max_length=255)
    allowed_uses: list[str] = Field(default_factory=lambda: ["resume_assistance"])
    default_visibility: str = "private"


class ArtifactPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    source_url: HttpUrl | None = None
    issuer: str | None = Field(default=None, max_length=255)
    retention_until: datetime | None = None


class PermissionPatch(BaseModel):
    allowed_uses: list[str]
    default_visibility: str


class EvidenceLinkBody(BaseModel):
    artifact_id: str
    relationship: str = "supports"
    access_scope: str = "private"


class ResumeVersionBody(BaseModel):
    created_reason: str = "manual_edit"


class ClaimMergeBody(BaseModel):
    claim_ids: list[str] = Field(min_length=2, max_length=20)
    text: str = Field(min_length=1, max_length=20000)


class ClaimSplitBody(BaseModel):
    texts: list[str] = Field(min_length=2, max_length=20)


@router.get("/career-passport/overview")
async def overview(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user_id = _candidate(current_user)
    counts = {}
    for key, model, condition in (
        ("experiences", CareerExperience, CareerExperience.user_id == user_id),
        ("claims", ResumeClaim, ResumeClaim.user_id == user_id),
        ("artifacts", EvidenceArtifact, (EvidenceArtifact.owner_user_id == user_id) & EvidenceArtifact.deleted_at.is_(None)),
        ("resume_versions", ResumeVersion, ResumeVersion.user_id == user_id),
    ):
        counts[key] = int(await db.scalar(select(func.count()).select_from(model).where(condition)) or 0)
    open_claims = (
        await db.execute(
            select(ResumeClaim).where(
                ResumeClaim.user_id == user_id,
                ResumeClaim.workflow_state == "open",
            ).order_by(ResumeClaim.updated_at.desc()).limit(20)
        )
    ).scalars().all()
    return {"counts": counts, "open_claims": [{"id": str(row.id), "text": row.current_text, "confirmation_state": row.confirmation_state} for row in open_claims]}


@router.post("/career-passport/import-resumes")
async def import_resumes_to_memory(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Idempotently project existing resumes into the career-memory network."""
    user_id = _candidate(current_user)
    resumes = (
        await db.execute(
            select(Resume)
            .where(Resume.user_id == user_id)
            .order_by(Resume.uploaded_at.asc())
        )
    ).scalars().all()
    claim_count = 0
    for resume in resumes:
        claims = await sync_resume_claims(
            db,
            resume,
            actor_id=user_id,
            reason="career_memory_import",
        )
        claim_count += len(claims)
    await db.commit()
    experience_count = int(
        await db.scalar(
            select(func.count())
            .select_from(CareerExperience)
            .where(
                CareerExperience.user_id == user_id,
                CareerExperience.workflow_state != "withdrawn",
            )
        )
        or 0
    )
    return {
        "resumes_scanned": len(resumes),
        "claims_linked": claim_count,
        "experiences": experience_count,
    }


@router.get("/career-passport/timeline")
async def timeline(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = _candidate(current_user)
    experiences = (
        await db.execute(
            select(CareerExperience).where(CareerExperience.user_id == user_id).order_by(CareerExperience.start_date.desc(), CareerExperience.created_at.desc())
        )
    ).scalars().all()
    versions = (
        await db.execute(
            select(ResumeVersion).where(ResumeVersion.user_id == user_id).order_by(ResumeVersion.created_at.desc())
        )
    ).scalars().all()
    items = [
        {"type": "experience", "occurred_at": (row.start_date.isoformat() if row.start_date else (row.created_at.isoformat() if row.created_at else None)), "data": serialize_experience(row)}
        for row in experiences
    ] + [
        {"type": "resume_version", "occurred_at": row.created_at.isoformat() if row.created_at else None, "data": {"id": str(row.id), "resume_id": str(row.resume_id), "version_number": row.version_number, "created_reason": row.created_reason, "content_hash": row.content_hash}}
        for row in versions
    ]
    items.sort(key=lambda item: item["occurred_at"] or "", reverse=True)
    return {"items": items[offset : offset + limit], "page": {"offset": offset, "limit": limit, "total": len(items), "has_more": offset + limit < len(items)}}


@router.get("/career-passport/map")
async def passport_map(
    view: str = Query(default="timeline"),
    job_id: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if view not in {"timeline", "capability", "evidence", "job"}:
        raise HTTPException(status_code=422, detail="未知地图视图")
    if view == "job" and not job_id:
        raise HTTPException(status_code=422, detail="目标岗位视图需要 job_id")
    return await build_map(
        db,
        user_id=_candidate(current_user),
        view=view,
        job_id=job_id,
        offset=offset,
        limit=limit,
    )


@router.post("/career-passport/experiences")
async def create_experience(
    body: ExperienceBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    if body.experience_type not in EXPERIENCE_TYPES or body.date_precision not in {"day", "month", "year", "unknown"}:
        raise HTTPException(status_code=422, detail="经历类型或日期精度无效")
    if body.workflow_state not in {"active", "archived", "withdrawn"}:
        raise HTTPException(status_code=422, detail="经历状态无效")
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="career.experience.create",
        idempotency_key=idempotency_key,
        request_payload=body.model_dump(mode="json"),
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        row = CareerExperience(id=str(uuid.uuid4()), user_id=user_id, **body.model_dump())
        db.add(row)
        await db.flush()
        payload = {"experience": serialize_experience(row)}
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.patch("/career-passport/experiences/{experience_id}")
async def patch_experience(
    experience_id: str,
    body: ExperienceBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="career.experience.patch",
        idempotency_key=idempotency_key,
        request_payload={"experience_id": experience_id, **body.model_dump(mode="json")},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        row = await db.get(CareerExperience, experience_id)
        if not row or row.user_id != user_id:
            raise HTTPException(status_code=404, detail="经历不存在或无权访问")
        for key, value in body.model_dump().items():
            setattr(row, key, value)
        row.updated_at = now_utc()
        payload = {"experience": serialize_experience(row)}
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.post("/career-passport/experiences/{experience_id}/claims")
async def create_experience_claim(
    experience_id: str,
    body: ClaimCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="career.experience.claim",
        idempotency_key=idempotency_key,
        request_payload={"experience_id": experience_id, **body.model_dump()},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        experience = await db.get(CareerExperience, experience_id)
        resume = await db.get(Resume, body.resume_id)
        if not experience or experience.user_id != user_id or not resume or str(resume.user_id) != user_id:
            raise HTTPException(status_code=404, detail="经历或简历不存在")
        claim = ResumeClaim(
            id=str(uuid.uuid4()), resume_id=str(resume.id), user_id=user_id,
            career_experience_id=str(experience.id), source_key=f"manual:{uuid.uuid4()}",
            section="career_experience", field_path=body.field_path, claim_type=body.claim_type,
            original_text=body.text.strip(), current_text=body.text.strip(),
            origin_kind="manual", source_object_type="career_experience",
            source_object_id=str(experience.id),
        )
        db.add(claim)
        await db.flush()
        await _event(db, str(claim.id), "claim_created", actor_id=user_id, payload={"origin_kind": "manual"})
        payload = {"claim_id": str(claim.id)}
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.patch("/career-passport/claims/{claim_id}")
async def patch_claim(
    claim_id: str,
    body: ClaimPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="career.claim.patch",
        idempotency_key=idempotency_key,
        request_payload={"claim_id": claim_id, **body.model_dump(exclude_unset=True)},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        claim = await owned_claim(db, claim_id, user_id)
        if not claim:
            raise HTTPException(status_code=404, detail="主张不存在或无权访问")
        payload = body.model_dump(exclude_unset=True)
        if "career_experience_id" in payload and payload["career_experience_id"]:
            exp = await db.get(CareerExperience, payload["career_experience_id"])
            if not exp or exp.user_id != user_id:
                raise HTTPException(status_code=404, detail="经历不存在或无权访问")
        before = claim.current_text
        if "text" in payload:
            claim.current_text = payload.pop("text").strip()
            db.add(
                ClaimRevision(
                    claim_id=str(claim.id),
                    before_text=before,
                    after_text=claim.current_text,
                    rewrite_mode="manual",
                    rule_version="career-passport-v2",
                    created_by=user_id,
                )
            )
        for key, value in payload.items():
            setattr(claim, key, value)
        await _event(db, str(claim.id), "claim_updated", actor_id=user_id)
        response = {"claim_id": str(claim.id), "status": "updated"}
        gate.set_response(200, response)
        await db.commit()
        return response


async def _change_claim_state(
    db: AsyncSession,
    claim_id: str,
    user_id: str,
    action: str,
    *,
    commit: bool = True,
):
    claim = await owned_claim(db, claim_id, user_id)
    if not claim:
        raise HTTPException(status_code=404, detail="主张不存在或无权访问")
    if action == "confirm":
        claim.confirmation_state = "user_confirmed"
        claim.confirmed_at = now_utc()
    else:
        claim.confirmation_state = "withdrawn"
        claim.workflow_state = "withdrawn"
    await _event(db, str(claim.id), f"claim_{action}ed", actor_id=user_id)
    payload = {"claim_id": str(claim.id), "confirmation_state": claim.confirmation_state}
    if commit:
        await db.commit()
    return payload


@router.post("/career-passport/claims/{claim_id}/confirm")
async def confirm_claim(
    claim_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="career.claim.confirm",
        idempotency_key=idempotency_key,
        request_payload={"claim_id": claim_id, "action": "confirm"},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        payload = await _change_claim_state(db, claim_id, user_id, "confirm", commit=False)
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.post("/career-passport/claims/{claim_id}/withdraw")
async def withdraw_claim(
    claim_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="career.claim.withdraw",
        idempotency_key=idempotency_key,
        request_payload={"claim_id": claim_id, "action": "withdraw"},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        payload = await _change_claim_state(db, claim_id, user_id, "withdraw", commit=False)
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.post("/career-passport/claims/merge")
async def merge_claims(
    body: ClaimMergeBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="career.claim.merge",
        idempotency_key=idempotency_key,
        request_payload=body.model_dump(),
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        ids = list(dict.fromkeys(body.claim_ids))
        claims = (
            await db.execute(
                select(ResumeClaim).where(
                    ResumeClaim.id.in_(ids),
                    ResumeClaim.user_id == user_id,
                    ResumeClaim.workflow_state != "withdrawn",
                )
            )
        ).scalars().all()
        if len(claims) != len(ids):
            raise HTTPException(status_code=404, detail="一个或多个 Claim 不存在或无权访问")
        primary = claims[0]
        merged = ResumeClaim(
            id=str(uuid.uuid4()),
            resume_id=str(primary.resume_id),
            user_id=user_id,
            career_experience_id=primary.career_experience_id,
            source_key=f"merge:{uuid.uuid4()}",
            section=primary.section,
            field_path=primary.field_path,
            claim_type=primary.claim_type,
            original_text=body.text.strip(),
            current_text=body.text.strip(),
            origin_kind="manual",
            source_object_type="claim_merge",
            source_span={"claim_ids": ids},
        )
        db.add(merged)
        await db.flush()
        for claim in claims:
            claim.superseded_by_claim_id = str(merged.id)
            claim.workflow_state = "withdrawn"
            await _event(db, str(claim.id), "claim_merged", actor_id=user_id, payload={"merged_claim_id": str(merged.id)})
        await _event(db, str(merged.id), "claim_created_from_merge", actor_id=user_id, payload={"source_claim_ids": ids})
        payload = {"claim_id": str(merged.id), "source_claim_ids": ids}
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.post("/career-passport/claims/{claim_id}/split")
async def split_claim(
    claim_id: str,
    body: ClaimSplitBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="career.claim.split",
        idempotency_key=idempotency_key,
        request_payload={"claim_id": claim_id, **body.model_dump()},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        claim = await owned_claim(db, claim_id, user_id)
        if not claim or claim.workflow_state == "withdrawn":
            raise HTTPException(status_code=404, detail="Claim 不存在或无权访问")
        texts = [value.strip() for value in body.texts if value.strip()]
        if len(texts) < 2:
            raise HTTPException(status_code=422, detail="拆分后至少需要两个非空 Claim")
        children = []
        for text_value in texts:
            child = ResumeClaim(
                id=str(uuid.uuid4()),
                resume_id=str(claim.resume_id),
                user_id=user_id,
                career_experience_id=claim.career_experience_id,
                source_key=f"split:{uuid.uuid4()}",
                section=claim.section,
                field_path=claim.field_path,
                claim_type=claim.claim_type,
                original_text=text_value,
                current_text=text_value,
                origin_kind="manual",
                source_object_type="claim_split",
                source_object_id=str(claim.id),
            )
            db.add(child)
            children.append(child)
        await db.flush()
        claim.workflow_state = "withdrawn"
        claim.superseded_by_claim_id = str(children[0].id)
        await _event(db, str(claim.id), "claim_split", actor_id=user_id, payload={"child_claim_ids": [str(row.id) for row in children]})
        for child in children:
            await _event(db, str(child.id), "claim_created_from_split", actor_id=user_id, payload={"source_claim_id": str(claim.id)})
        payload = {"source_claim_id": str(claim.id), "claim_ids": [str(row.id) for row in children]}
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.get("/career-passport/claims/{claim_id}/history")
async def claim_history(claim_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    claim = await owned_claim(db, claim_id, _candidate(current_user))
    if not claim:
        raise HTTPException(status_code=404, detail="主张不存在或无权访问")
    evidence = (await db.execute(select(ClaimEvidence).where(ClaimEvidence.claim_id == claim_id))).scalars().all()
    revisions = (await db.execute(select(ClaimRevision).where(ClaimRevision.claim_id == claim_id).order_by(ClaimRevision.created_at.desc()))).scalars().all()
    events = (await db.execute(select(ClaimEvent).where(ClaimEvent.claim_id == claim_id).order_by(ClaimEvent.created_at.desc()))).scalars().all()
    return {"claim": serialize_claim(claim, evidence, revisions, events)}


@router.post("/career-passport/claims/{claim_id}/chat/messages")
async def add_chat_message(
    claim_id: str,
    body: ChatMessageBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="career.claim.chat",
        idempotency_key=idempotency_key,
        request_payload={"claim_id": claim_id, **body.model_dump()},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        claim = await owned_claim(db, claim_id, user_id)
        if not claim:
            raise HTTPException(status_code=404, detail="主张不存在或无权访问")
        await _event(
            db,
            claim_id,
            "chat_user_message",
            actor_id=user_id,
            payload={
                "body": body.body,
                "question_goal": body.question_goal,
                "ai_generated": False,
            },
        )
        assistant = None
        session_id = None
        if body.ai_enabled:
            from .interview_sessions import create_session, next_question, serialize_question

            session = await create_session(
                db,
                user_id=user_id,
                mode="claim_clarification",
                resume_id=str(claim.resume_id),
                claim_id=str(claim.id),
                consent_snapshot={"resume_write": False},
                ai_enabled=False,
            )
            question = await next_question(db, session)
            session_id = str(session.id)
            if question is not None:
                assistant = serialize_question(question)
                await _event(
                    db,
                    claim_id,
                    "chat_assistant_message",
                    actor_id=user_id,
                    payload={
                        "body": question.question_text,
                        "question_goal": question.question_goal,
                        # Rules planned the question; Model Gateway was not invoked.
                        "ai_generated": False,
                        "generated_by": "rules",
                        "session_id": session_id,
                        "question_id": str(question.id),
                    },
                )
        payload = {
            "status": "recorded",
            # ai_connected means Model Gateway produced content; rules-only is clarification_connected.
            "ai_connected": False,
            "clarification_connected": bool(assistant),
            "generated_by": "rules" if assistant else None,
            "session_id": session_id,
            "assistant_message": assistant,
        }
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.get("/career-passport/claims/{claim_id}/chat/messages")
async def list_chat_messages(claim_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    claim = await owned_claim(db, claim_id, _candidate(current_user))
    if not claim:
        raise HTTPException(status_code=404, detail="主张不存在或无权访问")
    rows = (
        await db.execute(
            select(ClaimEvent)
            .where(ClaimEvent.claim_id == claim_id, ClaimEvent.event_type.like("chat_%"))
            .order_by(ClaimEvent.created_at.asc())
        )
    ).scalars().all()
    return {
        "messages": [
            {
                "id": str(row.id),
                "sender": "user" if row.event_type == "chat_user_message" else "assistant",
                **(row.payload or {}),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "ai_connected": False,
        "clarification_connected": any(
            row.event_type == "chat_assistant_message" for row in rows
        ),
    }


@router.post("/career-passport/resumes/{resume_id}/versions")
async def create_version(
    resume_id: str,
    body: ResumeVersionBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="career.resume.version",
        idempotency_key=idempotency_key,
        request_payload={"resume_id": resume_id, **body.model_dump()},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        resume = await db.get(Resume, resume_id)
        if not resume or str(resume.user_id) != user_id:
            raise HTTPException(status_code=404, detail="简历不存在或无权访问")
        try:
            version = await create_resume_version(
                db, resume, user_id=user_id, reason=body.created_reason, actor_id=user_id
            )
        except RuntimeError as exc:
            if str(exc) == "resume_version_conflict":
                raise HTTPException(status_code=409, detail="简历版本号冲突，请重试") from exc
            raise
        payload = {
            "version": {
                "id": str(version.id),
                "version_number": version.version_number,
                "content_hash": version.content_hash,
                "created_reason": version.created_reason,
            }
        }
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.post("/evidence-vault/artifacts/init-upload")
async def init_artifact(
    body: ArtifactInit,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    if body.artifact_type not in ARTIFACT_TYPES or not set(body.allowed_uses).issubset(ALLOWED_USES):
        raise HTTPException(status_code=422, detail="证据类型或用途无效")
    if body.default_visibility not in {"private", "application_selected"}:
        raise HTTPException(status_code=422, detail="可见范围无效")
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="vault.artifact.init",
        idempotency_key=idempotency_key,
        request_payload=body.model_dump(mode="json"),
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        row = EvidenceArtifact(
            id=str(uuid.uuid4()),
            owner_user_id=user_id,
            artifact_type=body.artifact_type,
            title=body.title.strip(),
            source_url=str(body.source_url) if body.source_url else None,
            issuer=body.issuer,
            allowed_uses=list(dict.fromkeys(body.allowed_uses)),
            default_visibility=body.default_visibility,
        )
        db.add(row)
        await db.flush()
        payload = {
            "artifact": serialize_artifact(row),
            "upload_required": body.artifact_type not in {"link", "user_statement"},
        }
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.post("/evidence-vault/artifacts/{artifact_id}/complete-upload")
async def complete_artifact_upload(
    artifact_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    row = await db.get(EvidenceArtifact, artifact_id)
    if not row or row.owner_user_id != user_id or row.deleted_at:
        raise HTTPException(status_code=404, detail="证据不存在或无权访问")
    if row.artifact_type in {"link", "user_statement"}:
        raise HTTPException(status_code=409, detail="该证据类型不需要上传文件")
    directory = os.getenv("EVIDENCE_VAULT_DIR") or (
        "/data/evidence-vault" if os.getenv("ENV") == "production" else "evidence_vault"
    )
    path, _ = await save_upload_safely(
        file,
        directory,
        allowed_extensions=EVIDENCE_FILE_EXTENSIONS,
    )
    object_key: str | None = None
    storage = None
    try:
        data = path.read_bytes()
        content_hash = hashlib.sha256(data).hexdigest()
        async with idempotent_write(
            db,
            user_id=user_id,
            scope="vault.artifact.upload",
            idempotency_key=idempotency_key,
            request_payload={
                "artifact_id": artifact_id,
                "filename": file.filename,
                "content_type": file.content_type,
                "size_bytes": len(data),
                "content_hash": content_hash,
            },
        ) as gate:
            if gate.replay is not None:
                return gate.replay
            scan = scan_bytes(data)
            if not scan.clean:
                scanner_unavailable = scan.detail in {
                    "scanner_not_configured",
                    "scanner_unavailable",
                    "unexpected_scanner_response",
                }
                raise HTTPException(
                    status_code=503 if scanner_unavailable else 422,
                    detail={
                        "error": "scanner_unavailable" if scanner_unavailable else "malware_detected",
                        "engine": scan.engine,
                        "detail": scan.detail,
                    },
                )
            storage = get_object_storage()
            object_key = evidence_object_key(
                user_id=user_id,
                artifact_id=artifact_id,
                filename_hint=path.suffix.lstrip(".") or "bin",
            )
            storage.put_bytes(object_key, data, content_type=file.content_type)
            row.object_ref = object_key
            row.content_hash = content_hash
            row.size_bytes = len(data)
            row.mime_type = file.content_type or "application/octet-stream"
            payload = {
                "artifact": serialize_artifact(row),
                "virus_scan": {"clean": True, "engine": scan.engine},
            }
            gate.set_response(200, payload)
            try:
                await db.commit()
            except Exception:
                if storage is not None and object_key is not None:
                    storage.delete(object_key)
                raise
            return payload
    finally:
        path.unlink(missing_ok=True)


@router.get("/evidence-vault/artifacts")
async def list_artifacts(offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user_id = _candidate(current_user)
    rows = (await db.execute(select(EvidenceArtifact).where(EvidenceArtifact.owner_user_id == user_id, EvidenceArtifact.deleted_at.is_(None)).order_by(EvidenceArtifact.created_at.desc()).offset(offset).limit(limit))).scalars().all()
    total = int(await db.scalar(select(func.count()).select_from(EvidenceArtifact).where(EvidenceArtifact.owner_user_id == user_id, EvidenceArtifact.deleted_at.is_(None))) or 0)
    return {"artifacts": [serialize_artifact(row) for row in rows], "page": {"offset": offset, "limit": limit, "total": total, "has_more": offset + limit < total}}


async def _owned_artifact(db: AsyncSession, artifact_id: str, user_id: str) -> EvidenceArtifact:
    row = await db.get(EvidenceArtifact, artifact_id)
    if not row or row.owner_user_id != user_id or row.deleted_at:
        raise HTTPException(status_code=404, detail="证据不存在或无权访问")
    return row


@router.get("/evidence-vault/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"artifact": serialize_artifact(await _owned_artifact(db, artifact_id, _candidate(current_user)))}


@router.get("/evidence-vault/artifacts/{artifact_id}/download-url")
async def artifact_download_url(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = _candidate(current_user)
    row = await _owned_artifact(db, artifact_id, user_id)
    if not row.object_ref:
        raise HTTPException(status_code=409, detail="证据文件尚未上传完成")
    s3 = maybe_s3_presign(row.object_ref)
    if s3 is not None:
        return {
            "url": s3.url,
            "expires_at": s3.expires_at,
            "backend": s3.backend,
        }
    signed = issue_download_token(
        artifact_id=str(row.id),
        user_id=user_id,
        object_ref=row.object_ref,
    )
    return {
        "url": signed.url,
        "expires_at": signed.expires_at,
        "backend": signed.backend,
    }


@router.get("/evidence-vault/artifacts/{artifact_id}/download")
async def artifact_download(
    artifact_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(EvidenceArtifact, artifact_id)
    if not row or row.deleted_at:
        raise HTTPException(status_code=404, detail="证据不存在或下载链接无效")
    if not row.object_ref:
        raise HTTPException(status_code=409, detail="证据文件尚未上传完成")
    try:
        verify_download_token(
            token=token,
            artifact_id=str(row.id),
            user_id=str(row.owner_user_id),
            object_ref=row.object_ref,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="证据不存在或下载链接无效") from exc
    storage = get_object_storage()
    data = storage.get_bytes(row.object_ref)
    return Response(
        content=data,
        media_type=row.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{row.title[:80]}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.patch("/evidence-vault/artifacts/{artifact_id}")
async def patch_artifact(
    artifact_id: str,
    body: ArtifactPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="vault.artifact.patch",
        idempotency_key=idempotency_key,
        request_payload={"artifact_id": artifact_id, **body.model_dump(exclude_unset=True)},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        row = await _owned_artifact(db, artifact_id, user_id)
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(row, key, str(value) if key == "source_url" and value else value)
        row.updated_at = now_utc()
        payload = {"artifact": serialize_artifact(row)}
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.delete("/evidence-vault/artifacts/{artifact_id}")
async def delete_artifact(
    artifact_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="vault.artifact.withdraw",
        idempotency_key=idempotency_key,
        request_payload={"artifact_id": artifact_id},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        row = await _owned_artifact(db, artifact_id, user_id)
        row.deleted_at = now_utc()
        row.withdrawn_at = row.deleted_at
        row.verification_status = "withdrawn"
        links = (
            await db.execute(
                select(ClaimEvidence).where(
                    ClaimEvidence.artifact_id == artifact_id,
                    ClaimEvidence.verification_status != "withdrawn",
                )
            )
        ).scalars().all()
        for link in links:
            link.verification_status = "withdrawn"
            link.withdrawn_at = row.deleted_at
        payload = {"status": "withdrawn", "artifact_id": artifact_id}
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.post("/evidence-vault/claims/{claim_id}/links")
async def link_artifact(
    claim_id: str,
    body: EvidenceLinkBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="vault.link.create",
        idempotency_key=idempotency_key,
        request_payload={"claim_id": claim_id, **body.model_dump()},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        claim = await owned_claim(db, claim_id, user_id)
        artifact = await _owned_artifact(db, body.artifact_id, user_id)
        if not claim:
            raise HTTPException(status_code=404, detail="主张不存在或无权访问")
        if artifact.withdrawn_at or artifact.verification_status == "withdrawn":
            raise HTTPException(status_code=409, detail="已撤回证据不能建立新关系")
        if body.relationship not in RELATIONSHIPS or body.access_scope not in {"private", "application_selected"}:
            raise HTTPException(status_code=422, detail="证据关系或访问范围无效")
        link = ClaimEvidence(
            id=str(uuid.uuid4()),
            claim_id=claim_id,
            artifact_id=str(artifact.id),
            evidence_type="document_reference",
            relationship=body.relationship,
            provided_by=user_id,
            link_created_by=user_id,
            link_method="manual",
            candidate_confirmed=True,
            access_scope=body.access_scope,
            verification_status="user_provided",
        )
        db.add(link)
        await _event(
            db,
            claim_id,
            "evidence_linked",
            actor_id=user_id,
            payload={"artifact_id": str(artifact.id), "relationship": body.relationship},
        )
        payload = {"link_id": str(link.id)}
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.delete("/evidence-vault/claims/{claim_id}/links/{link_id}")
async def unlink_artifact(
    claim_id: str,
    link_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="vault.link.withdraw",
        idempotency_key=idempotency_key,
        request_payload={"claim_id": claim_id, "link_id": link_id},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        claim = await owned_claim(db, claim_id, user_id)
        link = await db.get(ClaimEvidence, link_id)
        if not claim or not link or str(link.claim_id) != claim_id:
            raise HTTPException(status_code=404, detail="证据关系不存在或无权访问")
        link.verification_status = "withdrawn"
        link.withdrawn_at = now_utc()
        await _event(db, claim_id, "evidence_unlinked", actor_id=user_id, payload={"link_id": link_id})
        payload = {"status": "withdrawn"}
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.patch("/evidence-vault/artifacts/{artifact_id}/permissions")
async def patch_permissions(
    artifact_id: str,
    body: PermissionPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = _candidate(current_user)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="vault.artifact.permissions",
        idempotency_key=idempotency_key,
        request_payload={"artifact_id": artifact_id, **body.model_dump()},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        row = await _owned_artifact(db, artifact_id, user_id)
        if not set(body.allowed_uses).issubset(ALLOWED_USES) or body.default_visibility not in {"private", "application_selected"}:
            raise HTTPException(status_code=422, detail="用途或可见范围无效")
        row.allowed_uses = list(dict.fromkeys(body.allowed_uses))
        row.default_visibility = body.default_visibility
        payload = {"artifact": serialize_artifact(row)}
        gate.set_response(200, payload)
        await db.commit()
        return payload
