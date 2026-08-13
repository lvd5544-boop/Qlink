"""Bounded, auditable hypotheses for unresolved target-job diagnostics."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models_db import EvidenceArtifact, InferenceHypothesis, OptimizationIssue

HYPOTHESIS_RULE_VERSION = "c5-hypothesis-rules-v1"
ALLOWED_STATUSES = frozenset({"hypothesis", "user_confirmed", "evidence_supported", "rejected"})
MAX_HYPOTHESES_PER_ISSUE = 2


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def build_issue_hypotheses(
    *, issue_type: str, target_requirement_id: str | None, source_refs: list[Any]
) -> list[dict[str, Any]]:
    """Return at most two possibilities, always phrased as questions to verify."""
    requirement = str(target_requirement_id or "这项岗位要求").strip()
    refs = list(source_refs or [])
    if issue_type == "hard_constraint":
        return []
    candidates = [
        {
            "hypothesis_key": "experience_not_yet_recorded",
            "text": f"你可能有与“{requirement}”相关的经历，但目前材料中尚未记录。",
            "validation_question": "你是否有可以说明具体任务、个人贡献和结果的真实经历？",
            "source_refs": refs,
        },
        {
            "hypothesis_key": "transferable_experience_may_apply",
            "text": f"你已有经历中可能存在可迁移到“{requirement}”的相邻能力，但需要你确认对应关系。",
            "validation_question": "是否有一段已有经历能提供可核对的相似方法、工具或产出？",
            "source_refs": refs,
        },
    ]
    return candidates[:MAX_HYPOTHESES_PER_ISSUE]


async def create_issue_hypotheses(
    db: AsyncSession, *, issue: OptimizationIssue, has_candidate_claims: bool
) -> None:
    """Persist clarification hypotheses only when candidate facts are insufficient."""
    if has_candidate_claims:
        return
    for item in build_issue_hypotheses(
        issue_type=issue.issue_type,
        target_requirement_id=issue.target_requirement_id,
        source_refs=issue.source_refs or [],
    ):
        db.add(
            InferenceHypothesis(
                id=str(uuid.uuid4()),
                issue_id=str(issue.id),
                user_id=str(issue.user_id),
                hypothesis_key=item["hypothesis_key"],
                text=item["text"],
                validation_question=item["validation_question"],
                source_refs=item["source_refs"],
                status="hypothesis",
                rule_version=HYPOTHESIS_RULE_VERSION,
            )
        )


def serialize_hypothesis(row: InferenceHypothesis) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "hypothesis_key": row.hypothesis_key,
        "text": row.text,
        "validation_question": row.validation_question,
        "source_refs": row.source_refs or [],
        "status": row.status,
        "validation_evidence_id": row.validation_evidence_id,
        "rule_version": row.rule_version,
        "prompt_version": row.prompt_version,
        "model_version": row.model_version,
        "notice": "这是一条待验证假设；不会自动写入简历、Claim 或招聘结论。",
    }


async def hypotheses_by_issue(
    db: AsyncSession, *, issue_ids: list[str], user_id: str
) -> dict[str, list[InferenceHypothesis]]:
    if not issue_ids:
        return {}
    rows = (
        (
            await db.execute(
                select(InferenceHypothesis)
                .where(
                    InferenceHypothesis.issue_id.in_(issue_ids),
                    InferenceHypothesis.user_id == str(user_id),
                )
                .order_by(InferenceHypothesis.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[str, list[InferenceHypothesis]] = {}
    for row in rows:
        grouped.setdefault(str(row.issue_id), []).append(row)
    return grouped


async def resolve_hypothesis(
    db: AsyncSession,
    *,
    hypothesis_id: str,
    user_id: str,
    status: str,
    evidence_id: str | None = None,
) -> InferenceHypothesis:
    if status not in ALLOWED_STATUSES - {"hypothesis"}:
        raise ValueError("invalid_hypothesis_status")
    row = (
        await db.execute(
            select(InferenceHypothesis).where(
                InferenceHypothesis.id == str(hypothesis_id),
                InferenceHypothesis.user_id == str(user_id),
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise LookupError("hypothesis_not_found")
    if status == "evidence_supported":
        if not evidence_id:
            raise ValueError("hypothesis_evidence_required")
        artifact = await db.get(EvidenceArtifact, str(evidence_id))
        if (
            not artifact
            or str(artifact.owner_user_id) != str(user_id)
            or artifact.deleted_at is not None
            or artifact.withdrawn_at is not None
            or artifact.verification_status in {"rejected", "withdrawn"}
        ):
            raise PermissionError("evidence_not_owned")
        row.validation_evidence_id = str(artifact.id)
    else:
        row.validation_evidence_id = None
    row.status = status
    row.validated_at = _now_utc()
    await db.flush()
    return row
