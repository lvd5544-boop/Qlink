"""
resume_suggestions 表读写：记录 pending / applied / dismissed 状态。
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models_db import ResumeSuggestion


def _row_to_dict(row: ResumeSuggestion) -> dict:
    patch = row.patch if isinstance(row.patch, dict) else (row.patch or {})
    action = (patch or {}).get("action") or "fill_field"
    requires_evidence = bool(
        (patch or {}).get("requires_evidence") or action == "append_quantification"
    )
    needs_followup = bool((patch or {}).get("needs_followup") or requires_evidence)
    return {
        "id": row.suggestion_key,
        "db_id": row.id,
        "suggestion_key": row.suggestion_key,
        "resume_id": row.resume_id,
        "job_id": row.job_id,
        "source": row.source,
        "section": row.section,
        "field_path": row.field_path,
        "title": row.title,
        "description": row.description,
        "priority": row.priority,
        "issue": row.issue,
        "advice": row.advice,
        "original_text": row.original_text,
        "suggested_text": row.suggested_text,
        "section_label": row.section_label,
        "patch": patch,
        "status": row.status,
        "score_delta": row.score_delta,
        "requires_evidence": requires_evidence,
        "needs_followup": needs_followup,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def list_pending_suggestions(db: AsyncSession, resume_id: str) -> List[dict]:
    stmt = (
        select(ResumeSuggestion)
        .where(
            ResumeSuggestion.resume_id == resume_id,
            ResumeSuggestion.status == "pending",
        )
        .order_by(ResumeSuggestion.created_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_row_to_dict(r) for r in rows]


async def get_suggestion_by_id(
    db: AsyncSession,
    suggestion_id: str,
    resume_id: Optional[str] = None,
) -> Optional[ResumeSuggestion]:
    row = await db.get(ResumeSuggestion, suggestion_id)
    if not row:
        return None
    if resume_id and row.resume_id != resume_id:
        return None
    return row


async def get_suggestion_by_key(
    db: AsyncSession,
    resume_id: str,
    suggestion_key: str,
) -> Optional[ResumeSuggestion]:
    stmt = select(ResumeSuggestion).where(
        ResumeSuggestion.resume_id == resume_id,
        ResumeSuggestion.suggestion_key == suggestion_key,
    )
    return (await db.execute(stmt)).scalars().first()


async def sync_suggestions_for_source(
    db: AsyncSession,
    resume_id: str,
    source: str,
    actionable_items: List[dict],
    job_id: Optional[str] = None,
) -> List[dict]:
    """
    同步某来源的建议到 DB：
    - 已 applied/dismissed 的保留
    - pending 的按 suggestion_key 更新或新增
    - 不在新列表中的 pending 删除
    """
    stmt = select(ResumeSuggestion).where(
        ResumeSuggestion.resume_id == resume_id,
        ResumeSuggestion.source == source,
    )
    existing = (await db.execute(stmt)).scalars().all()
    existing_by_key = {r.suggestion_key: r for r in existing}
    new_keys = {item["id"] for item in actionable_items}

    for row in existing:
        if row.status == "pending" and row.suggestion_key not in new_keys:
            await db.delete(row)

    for item in actionable_items:
        key = item["id"]
        patch = dict(item.get("patch") or {})
        if item.get("requires_evidence"):
            patch["requires_evidence"] = True
        if item.get("needs_followup"):
            patch["needs_followup"] = True
        payload = {
            "resume_id": resume_id,
            "job_id": job_id or item.get("job_id"),
            "source": item.get("source") or source,
            "suggestion_key": key,
            "section": patch.get("section") or item.get("section"),
            "field_path": item.get("field_path") or patch.get("field_path"),
            "title": item.get("title"),
            "description": item.get("description"),
            "priority": item.get("priority") or "中",
            "issue": item.get("issue"),
            "advice": item.get("advice"),
            "original_text": item.get("original_text"),
            "suggested_text": item.get("suggested_text"),
            "section_label": item.get("section_label"),
            "patch": patch,
            "status": "pending",
        }
        row = existing_by_key.get(key)
        if row and row.status in ("applied", "dismissed"):
            continue
        if row:
            for k, v in payload.items():
                setattr(row, k, v)
        else:
            db.add(ResumeSuggestion(**payload))

    await db.commit()
    return await list_pending_suggestions(db, resume_id)


async def mark_suggestion_status(
    db: AsyncSession,
    suggestion_id: str,
    status: str,
    *,
    score_delta: Optional[float] = None,
) -> Optional[dict]:
    row = await db.get(ResumeSuggestion, suggestion_id)
    if not row:
        return None
    row.status = status
    if score_delta is not None:
        row.score_delta = score_delta
    await db.commit()
    await db.refresh(row)
    return _row_to_dict(row)


async def mark_suggestion_by_key(
    db: AsyncSession,
    resume_id: str,
    suggestion_key: str,
    status: str,
    *,
    score_delta: Optional[float] = None,
) -> Optional[dict]:
    stmt = select(ResumeSuggestion).where(
        ResumeSuggestion.resume_id == resume_id,
        ResumeSuggestion.suggestion_key == suggestion_key,
    )
    row = (await db.execute(stmt)).scalars().first()
    if not row:
        return None
    row.status = status
    if score_delta is not None:
        row.score_delta = score_delta
    await db.commit()
    await db.refresh(row)
    return _row_to_dict(row)
