"""HTTP boundary for the Claim Passport; all reads are object-authorized."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .claim_passport import (
    add_evidence,
    serialize_claim,
    sync_resume_claims,
    withdraw_evidence,
)
from .database import get_db
from .models_db import (
    ClaimApplicationLink,
    ClaimEvidence,
    ClaimEvent,
    ClaimRevision,
    JobApplication,
    JobDescription,
    Resume,
    ResumeClaim,
    User,
)

router = APIRouter(tags=["Claim Passport"])


class EvidenceCreateRequest(BaseModel):
    evidence_type: str = Field(default="user_statement")
    summary: str = Field(min_length=1, max_length=8000)
    source: str | None = Field(default=None, max_length=2000)


async def _owned_resume(db: AsyncSession, resume_id: str, user: User) -> Resume:
    resume = await db.get(Resume, resume_id)
    if not resume or resume.user_id != str(user.id):
        raise HTTPException(status_code=404, detail="简历不存在或无权访问")
    return resume


async def _claims_payload(db: AsyncSession, resume_id: str) -> list[dict]:
    claims = (
        (
            await db.execute(
                select(ResumeClaim)
                .where(ResumeClaim.resume_id == str(resume_id))
                .order_by(ResumeClaim.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    claim_ids = [str(row.id) for row in claims]
    evidence_by_claim: dict[str, list] = defaultdict(list)
    revisions_by_claim: dict[str, list] = defaultdict(list)
    events_by_claim: dict[str, list] = defaultdict(list)
    if claim_ids:
        evidence = (
            await db.execute(
                select(ClaimEvidence)
                .where(ClaimEvidence.claim_id.in_(claim_ids))
                .order_by(ClaimEvidence.created_at.desc())
            )
        ).scalars()
        revisions = (
            await db.execute(
                select(ClaimRevision)
                .where(ClaimRevision.claim_id.in_(claim_ids))
                .order_by(ClaimRevision.created_at.desc())
            )
        ).scalars()
        events = (
            await db.execute(
                select(ClaimEvent)
                .where(ClaimEvent.claim_id.in_(claim_ids))
                .order_by(ClaimEvent.created_at.desc())
            )
        ).scalars()
        for item in evidence:
            evidence_by_claim[str(item.claim_id)].append(item)
        for item in revisions:
            revisions_by_claim[str(item.claim_id)].append(item)
        for item in events:
            events_by_claim[str(item.claim_id)].append(item)
    return [
        serialize_claim(
            row,
            evidence_by_claim[str(row.id)],
            revisions_by_claim[str(row.id)],
            events_by_claim[str(row.id)],
        )
        for row in claims
    ]


@router.post("/resumes/{resume_id}/claims/sync")
async def sync_claims_endpoint(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await _owned_resume(db, resume_id, current_user)
    await sync_resume_claims(
        db, resume, actor_id=str(current_user.id), reason="candidate_requested_sync"
    )
    await db.commit()
    return {"resume_id": str(resume.id), "claims": await _claims_payload(db, str(resume.id))}


@router.get("/resumes/{resume_id}/claims")
async def list_claims_endpoint(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_resume(db, resume_id, current_user)
    return {"resume_id": resume_id, "claims": await _claims_payload(db, resume_id)}


@router.post("/resumes/{resume_id}/claims/{claim_id}/evidence")
async def add_claim_evidence_endpoint(
    resume_id: str,
    claim_id: str,
    body: EvidenceCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_resume(db, resume_id, current_user)
    claim = await db.get(ResumeClaim, claim_id)
    if not claim or claim.resume_id != str(resume_id):
        raise HTTPException(status_code=404, detail="主张不存在或无权访问")
    if body.evidence_type not in {"user_statement", "metric_context", "document_reference"}:
        raise HTTPException(status_code=422, detail="候选人不能伪造招聘方复核证据")
    evidence = await add_evidence(
        db,
        claim,
        actor_id=str(current_user.id),
        evidence_type=body.evidence_type,
        summary=body.summary,
        source=body.source,
    )
    await db.commit()
    return {"status": "ok", "claim_id": str(claim.id), "evidence_id": str(evidence.id)}


@router.delete("/resumes/{resume_id}/claims/evidence/{evidence_id}")
async def withdraw_claim_evidence_endpoint(
    resume_id: str,
    evidence_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_resume(db, resume_id, current_user)
    evidence = await db.get(ClaimEvidence, evidence_id)
    if not evidence:
        raise HTTPException(status_code=404, detail="证据不存在或无权访问")
    claim = await db.get(ResumeClaim, evidence.claim_id)
    if not claim or claim.resume_id != str(resume_id):
        raise HTTPException(status_code=404, detail="证据不存在或无权访问")
    try:
        await withdraw_evidence(db, evidence, actor_id=str(current_user.id))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await db.commit()
    return {"status": "withdrawn", "evidence_id": evidence_id}


@router.get("/applications/{application_id}/claim-passport")
async def application_claim_passport_endpoint(
    application_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    application = await db.get(JobApplication, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="申请不存在或无权访问")
    if current_user.role == "candidate":
        allowed = application.candidate_id == str(current_user.id)
    elif current_user.role == "employer":
        job = await db.get(JobDescription, application.job_id)
        allowed = bool(
            job
            and job.employer_id == str(current_user.id)
            and application.employer_id == str(current_user.id)
        )
    else:
        allowed = False
    if not allowed:
        raise HTTPException(status_code=404, detail="申请不存在或无权访问")

    links = (
        await db.execute(
            select(ClaimApplicationLink, ResumeClaim)
            .join(ResumeClaim, ResumeClaim.id == ClaimApplicationLink.claim_id)
            .where(ClaimApplicationLink.application_id == str(application.id))
            .order_by(ClaimApplicationLink.created_at.asc())
        )
    ).all()
    # Employers see only immutable submission snapshots, never later private evidence.
    source_labels = {
        "supported_by_user_evidence": "有用户证据支持",
        "not_enough_information": "用户自述",
        "conflict_detected": "存在待处理冲突",
    }
    return {
        "application_id": str(application.id),
        "claims": [
            {
                "claim_id": str(link.claim_id),
                "claim_type": claim.claim_type,
                "field_path": claim.field_path,
                "text_snapshot": link.text_snapshot,
                "evidence_state": link.evidence_state_snapshot,
                "workflow_state": link.workflow_state_snapshot,
                "employer_reviewed_at": link.employer_reviewed_at.isoformat()
                if link.employer_reviewed_at
                else None,
                "source_label": source_labels.get(link.evidence_state_snapshot, "用户自述"),
            }
            for link, claim in links
        ],
    }
