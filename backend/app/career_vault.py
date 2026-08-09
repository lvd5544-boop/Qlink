"""PR11 Career Passport and Evidence Vault domain services."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models_db import (
    CareerExperience,
    ClaimEvidence,
    ClaimRevision,
    EvidenceArtifact,
    JobDescription,
    Resume,
    ResumeClaim,
    ResumeVersion,
    ResumeVersionClaimLink,
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def canonical_hash(parsed: dict[str, Any], raw_text: str | None) -> str:
    payload = json.dumps(
        {"parsed": parsed or {}, "raw_text": raw_text or ""},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def owned_claim(db: AsyncSession, claim_id: str, user_id: str) -> ResumeClaim | None:
    return (
        await db.execute(
            select(ResumeClaim).where(
                ResumeClaim.id == str(claim_id),
                ResumeClaim.user_id == str(user_id),
            )
        )
    ).scalar_one_or_none()


async def _lock_resume_version_number(db: AsyncSession, resume_id: str) -> None:
    """Serialize version_number allocation per resume on PostgreSQL."""
    if db.bind and db.bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
            {"identity": f"resume_version:{resume_id}"},
        )


async def create_resume_version(
    db: AsyncSession,
    resume: Resume,
    *,
    user_id: str,
    reason: str,
    actor_id: str,
) -> ResumeVersion:
    if str(resume.user_id or "") != str(user_id):
        raise PermissionError("resume_not_owned")

    await _lock_resume_version_number(db, str(resume.id))
    latest = await db.scalar(
        select(func.max(ResumeVersion.version_number)).where(
            ResumeVersion.resume_id == str(resume.id)
        )
    )
    version = ResumeVersion(
        id=str(uuid.uuid4()),
        resume_id=str(resume.id),
        user_id=str(user_id),
        version_number=int(latest or 0) + 1,
        parsed_json_snapshot=deepcopy(resume.parsed_json or {}),
        raw_text_snapshot=resume.raw_text,
        content_hash=canonical_hash(resume.parsed_json or {}, resume.raw_text),
        created_reason=reason,
        created_by=str(actor_id),
    )
    db.add(version)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise RuntimeError("resume_version_conflict") from exc

    claims = (
        (
            await db.execute(
                select(ResumeClaim).where(
                    ResumeClaim.resume_id == str(resume.id),
                    ResumeClaim.workflow_state != "withdrawn",
                )
            )
        )
        .scalars()
        .all()
    )
    for claim in claims:
        evidence_ids = (
            (
                await db.execute(
                    select(ClaimEvidence.id).where(
                        ClaimEvidence.claim_id == str(claim.id),
                        ClaimEvidence.verification_status != "withdrawn",
                    )
                )
            )
            .scalars()
            .all()
        )
        revision = (
            await db.execute(
                select(ClaimRevision)
                .where(ClaimRevision.claim_id == str(claim.id))
                .order_by(ClaimRevision.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        db.add(
            ResumeVersionClaimLink(
                id=str(uuid.uuid4()),
                resume_version_id=str(version.id),
                claim_id=str(claim.id),
                claim_revision_id=str(revision.id) if revision else None,
                field_path=claim.field_path,
                text_snapshot=claim.current_text,
                evidence_ids_snapshot=[str(value) for value in evidence_ids],
                fidelity_result_snapshot=(
                    deepcopy(revision.fidelity_result or {}) if revision else {}
                ),
            )
        )
    await db.flush()
    return version


def serialize_experience(row: CareerExperience) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "experience_type": row.experience_type,
        "organization": row.organization,
        "title": row.title,
        "start_date": row.start_date.isoformat() if row.start_date else None,
        "end_date": row.end_date.isoformat() if row.end_date else None,
        "date_precision": row.date_precision,
        "description": row.description,
        "source_kind": row.source_kind,
        "workflow_state": row.workflow_state,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def serialize_artifact(row: EvidenceArtifact) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "artifact_type": row.artifact_type,
        "title": row.title,
        "source_url": row.source_url,
        "content_hash": row.content_hash,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "issuer": row.issuer,
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        "verification_status": row.verification_status,
        "allowed_uses": row.allowed_uses or [],
        "default_visibility": row.default_visibility,
        "retention_until": row.retention_until.isoformat() if row.retention_until else None,
        "withdrawn_at": row.withdrawn_at.isoformat() if row.withdrawn_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "upload_complete": bool(row.object_ref or row.artifact_type in {"link", "user_statement"}),
        "has_file": bool(row.object_ref),
    }


_DATE_ONLY = re.compile(
    r"^\s*(?:(?:19|20)\d{2}(?:[./-]\d{1,2})?"
    r"(?:\s*(?:-|–|—|to|至)\s*(?:(?:19|20)\d{2}(?:[./-]\d{1,2})?|present|至今))?)\s*$",
    re.I,
)
_CAPABILITY_ALIASES = {
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "sql": "SQL",
    "机器学习": "机器学习",
    "machine learning": "机器学习",
    "数据分析": "数据分析",
    "data analysis": "数据分析",
    "项目管理": "项目管理",
    "project management": "项目管理",
    "产品设计": "产品设计",
    "product design": "产品设计",
    "用户研究": "用户研究",
    "user research": "用户研究",
}


def _is_semantic_claim(claim: ResumeClaim) -> bool:
    text_value = (claim.current_text or "").strip()
    return bool(text_value) and not _DATE_ONLY.fullmatch(text_value)


def _group_key(claim: ResumeClaim) -> tuple[str, int | None]:
    return claim.section, claim.item_index


def _project_type(section: str) -> str:
    return "project" if section == "projects" else "experience"


def _capability_names(claims: list[ResumeClaim]) -> list[str]:
    names: list[str] = []
    haystack = "\n".join(
        claim.current_text or ""
        for claim in claims
        if claim.section in {"work_experience", "projects"}
    ).casefold()
    for claim in claims:
        if claim.section == "skills" or claim.claim_type == "skill":
            name = (claim.current_text or "").strip()
            if name and name.casefold() not in {item.casefold() for item in names}:
                names.append(name)
    for keyword, label in _CAPABILITY_ALIASES.items():
        if keyword in haystack and label.casefold() not in {item.casefold() for item in names}:
            names.append(label)
    return names[:12]


def _entry_and_details(
    claims: list[ResumeClaim],
) -> tuple[
    dict[tuple[str, int | None], ResumeClaim], dict[tuple[str, int | None], list[ResumeClaim]]
]:
    entries: dict[tuple[str, int | None], ResumeClaim] = {}
    details: dict[tuple[str, int | None], list[ResumeClaim]] = {}
    for claim in claims:
        if not _is_semantic_claim(claim):
            continue
        key = _group_key(claim)
        if claim.claim_type == "entry":
            entries[key] = claim
        elif claim.section in {"work_experience", "projects"}:
            details.setdefault(key, []).append(claim)
    return entries, details


async def build_map(
    db: AsyncSession,
    *,
    user_id: str,
    view: str,
    job_id: str | None,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    claims = (
        (
            await db.execute(
                select(ResumeClaim)
                .where(
                    ResumeClaim.user_id == str(user_id),
                    ResumeClaim.workflow_state != "withdrawn",
                )
                .order_by(ResumeClaim.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    claim_ids = [str(row.id) for row in claims]
    links = []
    if claim_ids:
        links = (
            await db.execute(
                select(ClaimEvidence, EvidenceArtifact)
                .outerjoin(EvidenceArtifact, EvidenceArtifact.id == ClaimEvidence.artifact_id)
                .where(
                    ClaimEvidence.claim_id.in_(claim_ids),
                    ClaimEvidence.verification_status != "withdrawn",
                )
            )
        ).all()

    claims = [claim for claim in claims if _is_semantic_claim(claim)]
    entries, grouped_details = _entry_and_details(claims)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    if view == "timeline":
        experiences = (
            (
                await db.execute(
                    select(CareerExperience).where(
                        CareerExperience.user_id == str(user_id),
                        CareerExperience.workflow_state != "withdrawn",
                    )
                )
            )
            .scalars()
            .all()
        )
        for exp in experiences:
            nodes.append(
                {
                    "id": f"experience:{exp.id}",
                    "type": "experience",
                    "label": exp.title or exp.organization or "职业经历",
                    "meta": serialize_experience(exp),
                }
            )
        for key, claim in entries.items():
            node_id = f"claim:{claim.id}"
            nodes.append(
                {
                    "id": node_id,
                    "type": _project_type(claim.section),
                    "label": claim.current_text,
                    "meta": {
                        "claim_id": str(claim.id),
                        "section": claim.section,
                        "detail_count": len(grouped_details.get(key, [])),
                        "details": [
                            {"id": str(item.id), "text": item.current_text}
                            for item in grouped_details.get(key, [])[:8]
                        ],
                    },
                }
            )
            if claim.career_experience_id:
                edges.append(
                    {
                        "id": f"contains:{claim.id}",
                        "source": f"experience:{claim.career_experience_id}",
                        "target": node_id,
                        "relationship": "包含",
                    }
                )
    elif view == "capability":
        for capability in _capability_names(claims):
            capability_id = f"capability:{capability.casefold()}"
            matched_groups = []
            for key, details in grouped_details.items():
                detail_text = " ".join(item.current_text or "" for item in details).casefold()
                if capability.casefold() in detail_text:
                    matched_groups.append(key)
            nodes.append(
                {
                    "id": capability_id,
                    "type": "capability",
                    "label": capability,
                    "meta": {
                        "project_count": len(matched_groups),
                        "status": "有项目支撑" if matched_groups else "待关联项目",
                    },
                }
            )
            for key in matched_groups[:6]:
                entry = entries.get(key)
                if entry is None:
                    continue
                project_id = f"project:{entry.id}"
                if not any(node["id"] == project_id for node in nodes):
                    nodes.append(
                        {
                            "id": project_id,
                            "type": _project_type(entry.section),
                            "label": entry.current_text,
                            "meta": {
                                "claim_id": str(entry.id),
                                "detail_count": len(grouped_details.get(key, [])),
                                "details": [
                                    {"id": str(item.id), "text": item.current_text}
                                    for item in grouped_details.get(key, [])[:8]
                                ],
                            },
                        }
                    )
                edges.append(
                    {
                        "id": f"capability-project:{capability_id}:{entry.id}",
                        "source": capability_id,
                        "target": project_id,
                        "relationship": "在该项目/经历中使用",
                    }
                )
    elif view == "evidence":
        linked_claim_ids = {
            str(link.claim_id)
            for link, artifact in links
            if artifact is not None and not artifact.deleted_at and not artifact.withdrawn_at
        }
        for claim in claims:
            if str(claim.id) not in linked_claim_ids:
                continue
            nodes.append(
                {
                    "id": f"claim:{claim.id}",
                    "type": "claim",
                    "label": claim.current_text,
                    "meta": {
                        "state": claim.confirmation_state,
                        "relationship_count": sum(
                            1 for link, _ in links if str(link.claim_id) == str(claim.id)
                        ),
                    },
                }
            )
    elif view == "job":
        job = await db.get(JobDescription, job_id) if job_id else None
        if job is not None:
            required = (job.parsed_json or {}).get("required_skills") or []
            for item in required:
                name = item.get("name") if isinstance(item, dict) else str(item)
                if not name:
                    continue
                requirement_id = f"requirement:{name.lower()}"
                matched = [
                    claim for claim in claims if name.lower() in (claim.current_text or "").lower()
                ]
                nodes.append(
                    {
                        "id": requirement_id,
                        "type": "requirement",
                        "label": name,
                        "meta": {
                            "job_id": str(job.id),
                            "status": "evidence_found" if matched else "needs_clarification",
                            "matched_claim_count": len(matched),
                        },
                    }
                )
                for claim in matched:
                    claim_node_id = f"claim:{claim.id}"
                    if not any(node["id"] == claim_node_id for node in nodes):
                        nodes.append(
                            {
                                "id": claim_node_id,
                                "type": "claim",
                                "label": claim.current_text,
                                "meta": {
                                    "claim_id": str(claim.id),
                                    "state": claim.confirmation_state,
                                    "matched_requirement": name,
                                },
                            }
                        )
                    edges.append(
                        {
                            "id": f"requirement-claim:{name}:{claim.id}",
                            "source": requirement_id,
                            "target": claim_node_id,
                            "relationship": "已有相关 Claim（仍需人工确认）",
                        }
                    )
    else:
        for claim in claims:
            nodes.append(
                {
                    "id": f"claim:{claim.id}",
                    "type": "claim",
                    "label": claim.current_text,
                    "meta": {"state": claim.confirmation_state},
                }
            )

    visible_claim_node_ids = {node["id"] for node in nodes if node["type"] == "claim"}
    for link, artifact in links:
        if view not in {"evidence", "job"}:
            continue
        if artifact is None or artifact.deleted_at or artifact.withdrawn_at:
            continue
        if f"claim:{link.claim_id}" not in visible_claim_node_ids:
            continue
        artifact_id = f"artifact:{artifact.id}"
        if not any(node["id"] == artifact_id for node in nodes):
            nodes.append(
                {
                    "id": artifact_id,
                    "type": "evidence",
                    "label": artifact.title,
                    "meta": {"verification_status": artifact.verification_status},
                }
            )
        edges.append(
            {
                "id": f"evidence-link:{link.id}",
                "source": artifact_id,
                "target": f"claim:{link.claim_id}",
                "relationship": {
                    "supports": "支持",
                    "contradicts": "待澄清的不一致",
                    "related": "相关",
                }.get(link.relationship, "相关"),
                "meta": {"link_method": link.link_method},
            }
        )

    page_nodes = nodes[offset : offset + limit]
    visible_ids = {node["id"] for node in page_nodes}
    page_edges = [
        edge for edge in edges if edge["source"] in visible_ids and edge["target"] in visible_ids
    ]
    return {
        "view": view,
        "nodes": page_nodes,
        "edges": page_edges,
        "page": {
            "offset": offset,
            "limit": limit,
            "total": len(nodes),
            "has_more": offset + limit < len(nodes),
        },
        "privacy_boundary": "owner_authorized_server_projection",
        "job_id": str(job_id) if job_id else None,
    }
