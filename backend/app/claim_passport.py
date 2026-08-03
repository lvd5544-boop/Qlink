"""Claim Passport persistence and provenance rules.

The Passport records source and handling history.  It deliberately never
asserts that a resume statement has been independently verified as true.
"""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .claim_reasoning import extract_resume_claims
from .models_db import (
    CareerExperience,
    ClaimApplicationLink,
    ClaimEvidence,
    ClaimEvent,
    ClaimRevision,
    JobApplication,
    Resume,
    ResumeClaim,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _field_path(item: dict[str, Any]) -> str:
    section = str(item.get("section") or "")
    index = item.get("entry_index")
    if section in {"work_experience", "projects"} and index is not None:
        return f"{section}[{int(index)}].description"
    if section == "education" and index is not None:
        return f"education[{int(index)}]"
    return section or "summary"


def _experience_identity(
    experience_type: str, organization: str | None, title: str | None
) -> tuple[str, str, str]:
    normalize = lambda value: re.sub(r"\s+", " ", str(value or "")).strip().casefold()
    return experience_type, normalize(organization), normalize(title)


async def _sync_career_experiences(
    db: AsyncSession, resume: Resume
) -> dict[tuple[str, int], CareerExperience]:
    """Project resume sections into the user's long-lived career memory.

    Claims still belong to the source resume for auditability, while their
    ``career_experience_id`` links equivalent entries across resume versions.
    Manual experiences are reused but never overwritten by an import.
    """
    if not resume.user_id:
        return {}
    parsed = resume.parsed_json or {}
    imported: list[tuple[str, int, str, str | None, str | None, str | None]] = []
    for index, item in enumerate(parsed.get("work_experience") or []):
        imported.append((
            "work",
            index,
            "work_experience",
            item.get("company"),
            item.get("position"),
            item.get("description"),
        ))
    for index, item in enumerate(parsed.get("projects") or []):
        imported.append((
            "project",
            index,
            "projects",
            None,
            item.get("name") or item.get("role"),
            item.get("description"),
        ))
    education = str(parsed.get("education") or "").strip()
    school = str(parsed.get("school") or "").strip() or None
    degree = str(parsed.get("degree") or "").strip() or None
    if education or school or degree:
        imported.append(("education", 0, "education", school, degree or education, education))

    existing = (
        await db.execute(
            select(CareerExperience).where(
                CareerExperience.user_id == str(resume.user_id),
                CareerExperience.workflow_state != "withdrawn",
            )
        )
    ).scalars().all()
    by_identity = {
        _experience_identity(row.experience_type, row.organization, row.title): row
        for row in existing
        if row.organization or row.title
    }
    result: dict[tuple[str, int], CareerExperience] = {}
    for experience_type, index, section, organization, title, description in imported:
        if not (organization or title):
            continue
        identity = _experience_identity(experience_type, organization, title)
        row = by_identity.get(identity)
        if row is None:
            row = CareerExperience(
                user_id=str(resume.user_id),
                experience_type=experience_type,
                organization=organization,
                title=title,
                description=description,
                source_kind="resume_import",
                source_ref=f"resume:{resume.id}:{section}:{index}",
                workflow_state="active",
            )
            db.add(row)
            await db.flush()
            by_identity[identity] = row
        elif row.source_kind == "resume_import":
            # Refresh imported content, but preserve user-authored records.
            row.description = description or row.description
            row.workflow_state = "active"
        result[(section, index)] = row
    return result


async def _event(
    db: AsyncSession,
    claim_id: str,
    event_type: str,
    *,
    actor_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(
        ClaimEvent(
            claim_id=str(claim_id),
            event_type=event_type,
            actor_id=str(actor_id) if actor_id else None,
            payload=deepcopy(payload or {}),
        )
    )


async def sync_resume_claims(
    db: AsyncSession,
    resume: Resume,
    *,
    actor_id: str | None = None,
    reason: str = "resume_sync",
) -> list[ResumeClaim]:
    """Upsert extracted claims while preserving Passport UUIDs and original text."""
    experience_by_section = await _sync_career_experiences(db, resume)
    rows = (
        (await db.execute(select(ResumeClaim).where(ResumeClaim.resume_id == str(resume.id))))
        .scalars()
        .all()
    )
    by_source = {row.source_key: row for row in rows}
    result: list[ResumeClaim] = []
    active_source_keys: set[str] = set()
    for item in extract_resume_claims(resume.parsed_json or {}):
        source_key = str(item["id"])
        current = str(item.get("text") or "").strip()
        if not current:
            continue
        active_source_keys.add(source_key)
        row = by_source.get(source_key)
        if row is None:
            row = ResumeClaim(
                resume_id=str(resume.id),
                user_id=str(resume.user_id) if resume.user_id else None,
                source_key=source_key,
                section=str(item.get("section") or "summary"),
                item_index=item.get("entry_index"),
                field_path=_field_path(item),
                claim_type=str(item.get("claim_type") or "statement"),
                original_text=current,
                current_text=current,
                origin_kind="resume",
                source_object_type="resume",
                source_object_id=str(resume.id),
                career_experience_id=(
                    str(experience_by_section[(str(item.get("section")), int(item.get("entry_index")))].id)
                    if item.get("entry_index") is not None
                    and (str(item.get("section")), int(item.get("entry_index")))
                    in experience_by_section
                    else None
                ),
            )
            db.add(row)
            await db.flush()
            await _event(
                db,
                str(row.id),
                "claim_created",
                actor_id=actor_id,
                payload={"source_key": source_key, "reason": reason},
            )
        else:
            if not row.user_id and resume.user_id:
                row.user_id = str(resume.user_id)
            changed = row.current_text != current
            row.section = str(item.get("section") or row.section)
            row.item_index = item.get("entry_index")
            row.field_path = _field_path(item)
            row.claim_type = str(item.get("claim_type") or row.claim_type)
            row.current_text = current
            if item.get("entry_index") is not None:
                experience = experience_by_section.get(
                    (str(item.get("section")), int(item.get("entry_index")))
                )
                if experience is not None:
                    row.career_experience_id = str(experience.id)
            if changed:
                await _event(
                    db,
                    str(row.id),
                    "claim_text_synced",
                    actor_id=actor_id,
                    payload={"reason": reason},
                )
        result.append(row)
    for source_key, row in by_source.items():
        if source_key in active_source_keys or row.workflow_state == "withdrawn":
            continue
        row.workflow_state = "withdrawn"
        await _event(
            db,
            str(row.id),
            "claim_withdrawn",
            actor_id=actor_id,
            payload={"reason": reason, "source_key": source_key},
        )
    await db.flush()
    return result


async def claim_for_source_key(
    db: AsyncSession, resume_id: str, source_key: str | None
) -> ResumeClaim | None:
    if not source_key:
        return None
    return (
        (
            await db.execute(
                select(ResumeClaim).where(
                    ResumeClaim.resume_id == str(resume_id),
                    ResumeClaim.source_key == str(source_key),
                )
            )
        )
        .scalars()
        .first()
    )


async def claims_for_field_path(
    db: AsyncSession, resume_id: str, field_path: str
) -> list[ResumeClaim]:
    return list(
        (
            await db.execute(
                select(ResumeClaim).where(
                    ResumeClaim.resume_id == str(resume_id),
                    ResumeClaim.field_path == str(field_path),
                )
            )
        ).scalars()
    )


async def upsert_field_claim(
    db: AsyncSession,
    resume: Resume,
    *,
    field_path: str,
    text: str,
    actor_id: str | None = None,
    reason: str = "field_sync",
) -> ResumeClaim:
    """Stable field-level Claim used when a rewrite changes claim boundaries."""
    source_key = f"field:{field_path}"
    row = await claim_for_source_key(db, str(resume.id), source_key)
    current = text.strip()
    if row is None:
        row = ResumeClaim(
            resume_id=str(resume.id),
            user_id=str(resume.user_id) if resume.user_id else None,
            source_key=source_key,
            section=field_path.split("[", 1)[0].split(".", 1)[0],
            item_index=None,
            field_path=field_path,
            claim_type="field_revision",
            original_text=current,
            current_text=current,
            origin_kind="resume",
            source_object_type="resume",
            source_object_id=str(resume.id),
        )
        db.add(row)
        await db.flush()
        await _event(
            db,
            str(row.id),
            "claim_created",
            actor_id=actor_id,
            payload={"source_key": source_key, "reason": reason},
        )
    elif row.current_text != current:
        row.current_text = current
        await _event(
            db,
            str(row.id),
            "claim_text_synced",
            actor_id=actor_id,
            payload={"reason": reason},
        )
    return row


async def snapshot_application_claims(
    db: AsyncSession,
    application: JobApplication,
    resume: Resume,
    *,
    actor_id: str | None,
) -> list[ClaimApplicationLink]:
    """Make immutable, application-scoped Passport snapshots at submission."""
    claims = await sync_resume_claims(db, resume, actor_id=actor_id, reason="application_snapshot")
    existing = {
        link.claim_id
        for link in (
            await db.execute(
                select(ClaimApplicationLink).where(
                    ClaimApplicationLink.application_id == str(application.id)
                )
            )
        ).scalars()
    }
    created: list[ClaimApplicationLink] = []
    for claim in claims:
        if str(claim.id) in existing:
            continue
        link = ClaimApplicationLink(
            claim_id=str(claim.id),
            application_id=str(application.id),
            text_snapshot=claim.current_text,
            evidence_state_snapshot=claim.evidence_state,
            workflow_state_snapshot=claim.workflow_state,
        )
        db.add(link)
        created.append(link)
        await _event(
            db,
            str(claim.id),
            "application_snapshot_created",
            actor_id=actor_id,
            payload={"application_id": str(application.id)},
        )
    await db.flush()
    return created


async def add_evidence(
    db: AsyncSession,
    claim: ResumeClaim,
    *,
    actor_id: str,
    evidence_type: str,
    summary: str,
    source: str | None = None,
) -> ClaimEvidence:
    evidence = ClaimEvidence(
        claim_id=str(claim.id),
        evidence_type=evidence_type,
        summary=summary.strip(),
        source=(source or "").strip() or None,
        provided_by=str(actor_id),
        verification_status="user_provided",
    )
    db.add(evidence)
    claim.evidence_state = "supported_by_user_evidence"
    if claim.workflow_state == "open":
        claim.workflow_state = "answered"
    await db.flush()
    await _event(
        db,
        str(claim.id),
        "evidence_added",
        actor_id=actor_id,
        payload={"evidence_id": str(evidence.id), "evidence_type": evidence_type},
    )
    return evidence


async def note_clarification_requested(
    db: AsyncSession,
    claim: ResumeClaim,
    *,
    application_id: str,
    employer_id: str,
) -> None:
    """Record a workflow request without claiming the underlying fact is true."""
    if claim.workflow_state != "withdrawn":
        claim.workflow_state = "open"
    await _event(
        db,
        str(claim.id),
        "clarification_requested",
        actor_id=employer_id,
        payload={"application_id": str(application_id)},
    )


async def record_application_conflict(
    db: AsyncSession,
    claim: ResumeClaim,
    *,
    application_id: str,
    employer_id: str,
    reason: str,
) -> ClaimEvidence:
    """Record a review conflict as a workflow signal, never a truth verdict."""
    evidence = ClaimEvidence(
        claim_id=str(claim.id),
        evidence_type="employer_review",
        summary=reason.strip(),
        source=f"application:{application_id}:employer_review",
        provided_by=str(employer_id),
        verification_status="employer_reviewed",
    )
    db.add(evidence)
    claim.evidence_state = "conflict_detected"
    claim.workflow_state = "reviewed"
    link = (
        (
            await db.execute(
                select(ClaimApplicationLink).where(
                    ClaimApplicationLink.application_id == str(application_id),
                    ClaimApplicationLink.claim_id == str(claim.id),
                )
            )
        )
        .scalars()
        .first()
    )
    if link:
        link.audit_snapshot = {
            "review_state": "conflict_detected",
            "reason": reason.strip(),
            "recorded_at": _now().isoformat(),
        }
    await db.flush()
    await _event(
        db,
        str(claim.id),
        "conflict_detected",
        actor_id=employer_id,
        payload={"application_id": str(application_id), "reason": reason.strip()},
    )
    return evidence


async def withdraw_evidence(db: AsyncSession, evidence: ClaimEvidence, *, actor_id: str) -> None:
    if str(evidence.provided_by or "") != str(actor_id):
        raise PermissionError("只能撤回自己的补充说明")
    if evidence.verification_status == "withdrawn":
        return
    evidence.summary = None
    evidence.source = None
    evidence.verification_status = "withdrawn"
    evidence.withdrawn_at = _now()
    claim = await db.get(ResumeClaim, evidence.claim_id)
    if claim:
        active = (
            await db.execute(
                select(ClaimEvidence.id).where(
                    ClaimEvidence.claim_id == str(claim.id),
                    ClaimEvidence.verification_status != "withdrawn",
                )
            )
        ).first()
        if not active:
            claim.evidence_state = "not_enough_information"
            if claim.workflow_state != "withdrawn":
                claim.workflow_state = "open"
        await _event(
            db,
            str(claim.id),
            "evidence_withdrawn",
            actor_id=actor_id,
            payload={"evidence_id": str(evidence.id), "content_redacted": True},
        )


async def record_revision(
    db: AsyncSession,
    claim: ResumeClaim,
    *,
    actor_id: str,
    before_text: str,
    after_text: str,
    rewrite_mode: str | None = None,
    evidence_ids: Iterable[str] = (),
    fidelity_result: dict[str, Any] | None = None,
) -> ClaimRevision:
    revision = ClaimRevision(
        claim_id=str(claim.id),
        before_text=before_text,
        after_text=after_text,
        rewrite_mode=rewrite_mode,
        evidence_ids=list(dict.fromkeys(str(value) for value in evidence_ids if value)),
        rule_version="claim-passport-v1",
        fidelity_result=deepcopy(fidelity_result or {}),
        created_by=str(actor_id),
    )
    db.add(revision)
    claim.current_text = after_text
    await db.flush()
    await _event(
        db,
        str(claim.id),
        "revision_created",
        actor_id=actor_id,
        payload={"revision_id": str(revision.id), "rewrite_mode": rewrite_mode},
    )
    return revision


async def mark_application_claim_reviewed(
    db: AsyncSession,
    *,
    application_id: str,
    claim_id: str,
    employer_id: str,
) -> ClaimApplicationLink | None:
    link = (
        (
            await db.execute(
                select(ClaimApplicationLink).where(
                    ClaimApplicationLink.application_id == str(application_id),
                    ClaimApplicationLink.claim_id == str(claim_id),
                )
            )
        )
        .scalars()
        .first()
    )
    if link is None:
        return None
    link.employer_reviewed_at = _now()
    await _event(
        db,
        str(claim_id),
        "application_claim_reviewed",
        actor_id=employer_id,
        payload={"application_id": str(application_id)},
    )
    return link


async def application_claim_snapshot_summary(
    db: AsyncSession, application_id: str
) -> list[dict[str, Any]]:
    """Return only submission-time Passport state for downstream audits."""
    rows = (
        await db.execute(
            select(ClaimApplicationLink, ResumeClaim)
            .join(ResumeClaim, ResumeClaim.id == ClaimApplicationLink.claim_id)
            .where(ClaimApplicationLink.application_id == str(application_id))
            .order_by(ClaimApplicationLink.created_at.asc())
        )
    ).all()
    return [
        {
            "claim_id": str(link.claim_id),
            "claim_type": claim.claim_type,
            "field_path": claim.field_path,
            "text_snapshot": link.text_snapshot,
            "evidence_state": link.evidence_state_snapshot,
            "workflow_state": link.workflow_state_snapshot,
            "provenance_label": "用户自述，不构成事实认证",
        }
        for link, claim in rows
    ]


def serialize_claim(
    claim: ResumeClaim,
    evidence: list[ClaimEvidence],
    revisions: list[ClaimRevision],
    events: Iterable[ClaimEvent] = (),
) -> dict:
    section_labels = {
        "work_experience": "工作经历",
        "projects": "项目经历",
        "education": "教育背景",
        "skills": "技能",
        "name": "基本信息",
        "summary": "个人简介",
    }
    item_number = (claim.item_index + 1) if claim.item_index is not None else None
    source_locator = section_labels.get(claim.section, claim.section)
    if item_number is not None:
        source_locator = f"{source_locator} · 第 {item_number} 项"
    hierarchy_level = "entry" if claim.claim_type == "entry" else "detail"
    group_key = (
        f"{claim.section}:{claim.item_index}"
        if claim.item_index is not None
        else f"{claim.section}:root"
    )
    return {
        "id": str(claim.id),
        "source_key": claim.source_key,
        "section": claim.section,
        "item_index": claim.item_index,
        "field_path": claim.field_path,
        "claim_type": claim.claim_type,
        "hierarchy_level": hierarchy_level,
        "group_key": group_key,
        "source_locator": source_locator,
        "original_text": claim.original_text,
        "current_text": claim.current_text,
        "evidence_state": claim.evidence_state,
        "workflow_state": claim.workflow_state,
        "confirmation_state": claim.confirmation_state,
        "confirmed_at": claim.confirmed_at.isoformat() if claim.confirmed_at else None,
        "career_experience_id": claim.career_experience_id,
        "origin_kind": claim.origin_kind,
        "sensitivity_level": claim.sensitivity_level,
        "default_visibility": claim.default_visibility,
        "evidence": [
            {
                "id": str(item.id),
                "evidence_type": item.evidence_type,
                "summary": item.summary,
                "source": item.source,
                "verification_status": item.verification_status,
                "artifact_id": item.artifact_id,
                "relationship": item.relationship,
                "access_scope": item.access_scope,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in evidence
        ],
        "revisions": [
            {
                "id": str(item.id),
                "before_text": item.before_text,
                "after_text": item.after_text,
                "rewrite_mode": item.rewrite_mode,
                "evidence_ids": item.evidence_ids or [],
                "fidelity_result": item.fidelity_result or {},
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in revisions
        ],
        "events": [
            {
                "id": str(item.id),
                "event_type": item.event_type,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in events
        ],
    }
_DATE_ONLY_CLAIM = re.compile(
    r"^\s*(?:(?:19|20)\d{2}(?:[./-]\d{1,2})?"
    r"(?:\s*(?:-|–|—|to|至)\s*(?:(?:19|20)\d{2}(?:[./-]\d{1,2})?|present|至今))?)\s*$",
    re.I,
)


def is_context_only_claim(claim: ResumeClaim) -> bool:
    """Legacy date rows remain auditable in storage but are not product Claims."""
    return bool(_DATE_ONLY_CLAIM.fullmatch((claim.current_text or "").strip()))
