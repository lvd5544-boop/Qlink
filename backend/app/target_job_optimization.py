"""PR13 target-job diagnostics, faithful rewrites and readiness actions."""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .career_vault import canonical_hash, create_resume_version
from .claim_passport import sync_resume_claims
from .evidence_followup import assess_fidelity
from .models_db import (
    ClaimEvidence,
    EvidenceArtifact,
    JobDescription,
    OptimizationIssue,
    OptimizationIssueClaimLink,
    OptimizationStrategyOption,
    ReadinessAction,
    Resume,
    ResumeClaim,
    ResumePatchProposal,
    ResumeVersion,
)
from .potential_simulation import RULE_VERSION, build_simulation
from .personalized_guidance import build_job_guidance
from .resume_apply import apply_field_path, value_at_field_path
from .security import candidate_can_access_job

SCORING_VERSION = "hybrid_v2"
DIAGNOSTIC_CATEGORIES = (
    "expression",
    "evidence",
    "capability",
    "hard_constraint",
    "consistency",
    "structure_ats",
    "relevance",
    "differentiation",
    "career_narrative",
    "privacy_compliance",
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _category(issue_type: str) -> str:
    return {
        "presentation_gap": "expression",
        "evidence_gap": "evidence",
        "capability_gap": "capability",
        "hard_constraint": "hard_constraint",
        "credibility_risk": "consistency",
        "relevance_gap": "relevance",
        "differentiation_gap": "differentiation",
        "career_narrative_gap": "career_narrative",
    }.get(issue_type, "structure_ats")


CLARIFIABLE_ISSUE_TYPES = frozenset(
    {
        "presentation_gap",
        "evidence_gap",
        "capability_gap",
        "credibility_risk",
        "relevance_gap",
        "differentiation_gap",
        "career_narrative_gap",
    }
)


def route_state_for(
    *,
    issue_type: str,
    claim_ids: list[str],
    strategies: list[dict[str, Any]],
    development_confirmed: bool,
) -> tuple[str, str]:
    """Pick the candidate's next step for one diagnosed issue.

    A requirement that is simply absent from the resume can only reach
    ``clarify``. Only an explicit candidate action — selecting a development
    strategy for that requirement — may reach ``develop``.
    """
    if issue_type == "hard_constraint":
        return "constraint", "objective_constraint_checked_separately"
    if claim_ids and any(option.get("can_apply_now") for option in strategies):
        return "ready", "candidate_source_usable_now"
    if development_confirmed:
        return "develop", "candidate_selected_development_plan"
    if issue_type == "capability_gap":
        return "clarify", "missing_from_resume_needs_candidate_confirmation"
    if issue_type in CLARIFIABLE_ISSUE_TYPES:
        return "clarify", "candidate_source_incomplete"
    return "unknown", "insufficient_information_to_route"


def _severity(issue_type: str) -> str:
    if issue_type == "hard_constraint":
        return "blocker"
    if issue_type in {"capability_gap", "credibility_risk"}:
        return "high"
    if issue_type in {"evidence_gap", "relevance_gap", "career_narrative_gap"}:
        return "medium"
    return "low"


async def owned_inputs(
    db: AsyncSession, *, user_id: str, resume_id: str, job_id: str
) -> tuple[Resume, JobDescription, list[ResumeClaim]]:
    resume = await db.get(Resume, str(resume_id))
    if not resume or str(resume.user_id) != str(user_id):
        raise PermissionError("resume_not_owned")
    job = await db.get(JobDescription, str(job_id))
    if not job or not candidate_can_access_job(job, str(user_id)):
        raise ValueError("job_not_found")
    await sync_resume_claims(db, resume, actor_id=str(user_id), reason="pr13_diagnostic")
    claims = (
        (
            await db.execute(
                select(ResumeClaim).where(
                    ResumeClaim.resume_id == str(resume.id),
                    ResumeClaim.user_id == str(user_id),
                    ResumeClaim.workflow_state != "withdrawn",
                )
            )
        )
        .scalars()
        .all()
    )
    return resume, job, list(claims)


async def ensure_current_version(
    db: AsyncSession, resume: Resume, *, user_id: str
) -> ResumeVersion:
    content_hash = canonical_hash(resume.parsed_json or {}, resume.raw_text)
    latest = (
        await db.execute(
            select(ResumeVersion)
            .where(ResumeVersion.resume_id == str(resume.id))
            .order_by(ResumeVersion.version_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest and latest.content_hash == content_hash:
        return latest
    return await create_resume_version(
        db,
        resume,
        user_id=str(user_id),
        reason="target_diagnostic",
        actor_id=str(user_id),
    )


def _claim_snapshot(claims: list[ResumeClaim]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(row.id),
            "current_text": row.current_text,
            "field_path": row.field_path,
            "evidence_state": row.evidence_state,
        }
        for row in claims
    ]


async def generate_diagnostic(
    db: AsyncSession, *, user_id: str, resume_id: str, job_id: str
) -> str:
    resume, job, claims = await owned_inputs(
        db, user_id=user_id, resume_id=resume_id, job_id=job_id
    )
    version = await ensure_current_version(db, resume, user_id=user_id)
    result = build_simulation(
        resume.parsed_json or {},
        {**(job.parsed_json or {}), "_raw_text": job.raw_text or ""},
        job.title or "",
        _claim_snapshot(claims),
    )
    prior = (
        (
            await db.execute(
                select(OptimizationIssue).where(
                    OptimizationIssue.resume_id == str(resume.id),
                    OptimizationIssue.job_id == str(job.id),
                    OptimizationIssue.status == "open",
                )
            )
        )
        .scalars()
        .all()
    )
    for row in prior:
        row.status = "superseded"

    diagnostic_id = str(uuid.uuid4())
    for item in result["issues"]:
        issue = OptimizationIssue(
            id=str(uuid.uuid4()),
            diagnostic_id=diagnostic_id,
            user_id=str(user_id),
            resume_id=str(resume.id),
            resume_version_id=str(version.id),
            job_id=str(job.id),
            issue_key=item["issue_id"],
            issue_type=item["issue_type"],
            target_requirement_id=item.get("target_requirement_id"),
            diagnosis=item["diagnosis"],
            severity=_severity(item["issue_type"]),
            source_refs=item.get("source_refs") or [],
            rule_version=RULE_VERSION,
        )
        db.add(issue)
        await db.flush()
        for claim_id in item.get("claim_ids") or []:
            db.add(
                OptimizationIssueClaimLink(
                    id=str(uuid.uuid4()),
                    issue_id=str(issue.id),
                    claim_id=str(claim_id),
                    relation="gap" if item["issue_type"] == "evidence_gap" else "related",
                )
            )
        recommended_id = item.get("recommended_strategy_id")
        for option in item.get("strategy_options") or []:
            db.add(
                OptimizationStrategyOption(
                    id=str(uuid.uuid4()),
                    issue_id=str(issue.id),
                    strategy=option["strategy"],
                    title=option["title"],
                    why=option["why"],
                    requires_evidence=bool(option["requires_evidence"]),
                    can_apply_now=bool(option["can_apply_now"]),
                    next_action=option["next_action"],
                    affected_dimensions=option.get("affected_dimensions") or [],
                    time_horizon=option["time_horizon"],
                    user_cost=option["user_cost"],
                    hallucination_risk="low" if item.get("claim_ids") else "high",
                    recommended=option["strategy_id"] == recommended_id,
                    eligibility_reason=(
                        "存在可追溯 Claim，可在 Fidelity 复核后使用"
                        if item.get("claim_ids")
                        else "当前没有候选人事实来源，只能作为未来行动"
                    ),
                    counterfactual_snapshot={
                        "source_versions": result["source_versions"],
                        "selection_effects": result["selection_effects"],
                    },
                    expression_delta=result["expression_delta"],
                    evidence_delta=result["evidence_delta"],
                    capability_delta=result["capability_delta"],
                    rule_version=RULE_VERSION,
                    scoring_version=SCORING_VERSION,
                )
            )
    await db.flush()
    return diagnostic_id


async def serialize_diagnostic(
    db: AsyncSession, *, user_id: str, job_id: str, diagnostic_id: str
) -> dict[str, Any]:
    issues = (
        (
            await db.execute(
                select(OptimizationIssue)
                .where(
                    OptimizationIssue.diagnostic_id == str(diagnostic_id),
                    OptimizationIssue.user_id == str(user_id),
                    OptimizationIssue.job_id == str(job_id),
                )
                .order_by(OptimizationIssue.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    if not issues:
        raise LookupError("diagnostic_not_found")
    issue_ids = [str(row.id) for row in issues]
    strategies = (
        (
            await db.execute(
                select(OptimizationStrategyOption).where(
                    OptimizationStrategyOption.issue_id.in_(issue_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    links = (
        (
            await db.execute(
                select(OptimizationIssueClaimLink).where(
                    OptimizationIssueClaimLink.issue_id.in_(issue_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    strategies_by_issue: dict[str, list[OptimizationStrategyOption]] = {}
    for row in strategies:
        strategies_by_issue.setdefault(str(row.issue_id), []).append(row)
    claims_by_issue: dict[str, list[str]] = {}
    for row in links:
        claims_by_issue.setdefault(str(row.issue_id), []).append(str(row.claim_id))

    confirmed_development_keys = set(
        (
            await db.execute(
                select(OptimizationIssue.issue_key)
                .join(ReadinessAction, ReadinessAction.issue_id == OptimizationIssue.id)
                .where(
                    ReadinessAction.user_id == str(user_id),
                    ReadinessAction.job_id == str(job_id),
                    ReadinessAction.status != "abandoned",
                )
            )
        )
        .scalars()
        .all()
    )

    serialized: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in DIAGNOSTIC_CATEGORIES}
    severity_order = {"blocker": 0, "high": 1, "medium": 2, "low": 3}
    for row in sorted(issues, key=lambda item: severity_order[item.severity]):
        issue_claim_ids = claims_by_issue.get(str(row.id), [])
        issue_strategies = [
            serialize_strategy(value) for value in strategies_by_issue.get(str(row.id), [])
        ]
        route_state, route_reason = route_state_for(
            issue_type=row.issue_type,
            claim_ids=issue_claim_ids,
            strategies=issue_strategies,
            development_confirmed=row.issue_key in confirmed_development_keys,
        )
        item = {
            "id": str(row.id),
            "issue_key": row.issue_key,
            "issue_type": row.issue_type,
            "category": _category(row.issue_type),
            "route_state": route_state,
            "route_reason": route_reason,
            "target_requirement_id": row.target_requirement_id,
            "diagnosis": row.diagnosis,
            "severity": row.severity,
            "source_refs": row.source_refs or [],
            "claim_ids": issue_claim_ids,
            "status": row.status,
            "strategies": issue_strategies,
        }
        serialized.append(item)
        grouped[item["category"]].append(item)

    first = issues[0]
    resume = await db.get(Resume, str(first.resume_id))
    job = await db.get(JobDescription, str(first.job_id))
    claims = (
        (
            await db.execute(
                select(ResumeClaim).where(
                    ResumeClaim.resume_id == str(first.resume_id),
                    ResumeClaim.workflow_state != "withdrawn",
                )
            )
        )
        .scalars()
        .all()
    )
    simulation = build_simulation(
        resume.parsed_json or {},
        {**(job.parsed_json or {}), "_raw_text": job.raw_text or ""},
        job.title or "",
        _claim_snapshot(list(claims)),
    )
    personalized_guidance = build_job_guidance(
        resume_json=resume.parsed_json or {},
        job_json=job.parsed_json or {},
        job_title=job.title,
        issues=serialized,
    )
    return {
        "diagnostic_id": diagnostic_id,
        "resume_id": str(first.resume_id),
        "resume_version_id": str(first.resume_version_id),
        "job_id": str(first.job_id),
        "job_title": job.title,
        "issues": serialized,
        "categories": grouped,
        "personalized_guidance": personalized_guidance,
        "readiness": {
            "current": simulation["current_score"],
            "future_scenario": simulation["potential_score"],
            "expression_delta": simulation["expression_delta"],
            "evidence_delta": simulation["evidence_delta"],
            "capability_delta": simulation["capability_delta"],
            "notice": "未来行动仅为反事实情景，不会提高当前准备度；完成后仍需新增 Claim/Evidence 并重新诊断。",
            "scoring_version": SCORING_VERSION,
        },
        "decision_trace": {
            "observed_source_refs": simulation["source_versions"],
            "rules_fired": [row.issue_key for row in issues],
            "findings": [row.diagnosis for row in issues],
            "uncertainties": [
                "未被简历或 Evidence Vault 观察到的能力保持 unknown，不推断为不具备。"
            ],
            "recommended_next_actions": [value.title for value in strategies if value.recommended],
        },
    }


def serialize_strategy(row: OptimizationStrategyOption) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "strategy": row.strategy,
        "title": row.title,
        "why": row.why,
        "requires_evidence": bool(row.requires_evidence),
        "can_apply_now": bool(row.can_apply_now),
        "next_action": row.next_action,
        "affected_dimensions": row.affected_dimensions or [],
        "time_horizon": row.time_horizon,
        "user_cost": row.user_cost,
        "hallucination_risk": row.hallucination_risk,
        "recommended": bool(row.recommended),
        "eligibility_reason": row.eligibility_reason,
        "status": row.status,
    }


async def owned_issue(db: AsyncSession, *, issue_id: str, user_id: str) -> OptimizationIssue | None:
    return (
        await db.execute(
            select(OptimizationIssue).where(
                OptimizationIssue.id == str(issue_id),
                OptimizationIssue.user_id == str(user_id),
            )
        )
    ).scalar_one_or_none()


async def select_strategy(
    db: AsyncSession, *, issue: OptimizationIssue, strategy_id: str, user_id: str
) -> ReadinessAction:
    strategy = await db.get(OptimizationStrategyOption, str(strategy_id))
    if not strategy or str(strategy.issue_id) != str(issue.id):
        raise ValueError("strategy_not_in_issue")
    rows = (
        (
            await db.execute(
                select(OptimizationStrategyOption).where(
                    OptimizationStrategyOption.issue_id == str(issue.id)
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.status = "selected" if str(row.id) == str(strategy.id) else "available"
    existing = (
        await db.execute(
            select(ReadinessAction).where(
                ReadinessAction.user_id == str(user_id),
                ReadinessAction.strategy_id == str(strategy.id),
                ReadinessAction.status.in_(("planned", "in_progress")),
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    action = ReadinessAction(
        id=str(uuid.uuid4()),
        user_id=str(user_id),
        job_id=str(issue.job_id),
        issue_id=str(issue.id),
        strategy_id=str(strategy.id),
        action_type=strategy.next_action,
        title=strategy.title,
        description=strategy.why,
        expected_time_horizon=strategy.time_horizon,
        user_cost=strategy.user_cost,
    )
    db.add(action)
    await db.flush()
    return action


async def create_rewrite_preview(
    db: AsyncSession, *, issue: OptimizationIssue, strategy_id: str, user_id: str
) -> ResumePatchProposal:
    strategy = await db.get(OptimizationStrategyOption, str(strategy_id))
    if not strategy or str(strategy.issue_id) != str(issue.id):
        raise ValueError("strategy_not_in_issue")
    links = (
        (
            await db.execute(
                select(OptimizationIssueClaimLink).where(
                    OptimizationIssueClaimLink.issue_id == str(issue.id)
                )
            )
        )
        .scalars()
        .all()
    )
    claim_ids = [str(row.claim_id) for row in links]
    claims = []
    if claim_ids:
        claims = (
            (
                await db.execute(
                    select(ResumeClaim).where(
                        ResumeClaim.id.in_(claim_ids),
                        ResumeClaim.user_id == str(user_id),
                        ResumeClaim.workflow_state != "withdrawn",
                    )
                )
            )
            .scalars()
            .all()
        )
    if not claims:
        raise PermissionError("candidate_source_required")

    resume = await db.get(Resume, str(issue.resume_id))
    field_path = "summary"
    before_text = value_at_field_path(resume.parsed_json or {}, field_path)
    claim_texts = list(
        dict.fromkeys(row.current_text.strip() for row in claims if row.current_text.strip())
    )
    source_corpus = "；".join([value for value in [before_text, *claim_texts] if value])
    after_text = source_corpus
    fidelity = assess_fidelity(source_corpus, after_text)
    evidence_ids = (
        (
            await db.execute(
                select(ClaimEvidence.artifact_id).where(
                    ClaimEvidence.claim_id.in_(claim_ids),
                    ClaimEvidence.artifact_id.is_not(None),
                    ClaimEvidence.verification_status != "withdrawn",
                )
            )
        )
        .scalars()
        .all()
    )
    proposal = ResumePatchProposal(
        id=str(uuid.uuid4()),
        user_id=str(user_id),
        resume_id=str(resume.id),
        resume_version_id=str(issue.resume_version_id),
        target_job_id=str(issue.job_id),
        issue_id=str(issue.id),
        strategy_id=str(strategy.id),
        field_path=field_path,
        before_text=before_text,
        after_text=after_text,
        atomic_changes=[
            {
                "operation": "replace",
                "field_path": field_path,
                "before": before_text,
                "after": after_text,
            }
        ],
        source_claim_ids=claim_ids,
        source_evidence_ids=[str(value) for value in evidence_ids if value],
        source_answer_ids=[],
        fidelity_result=fidelity,
        status="needs_confirmation",
        rule_version=RULE_VERSION,
    )
    db.add(proposal)
    await db.flush()
    return proposal


async def owned_proposal(
    db: AsyncSession, *, proposal_id: str, user_id: str
) -> ResumePatchProposal | None:
    return (
        await db.execute(
            select(ResumePatchProposal).where(
                ResumePatchProposal.id == str(proposal_id),
                ResumePatchProposal.user_id == str(user_id),
            )
        )
    ).scalar_one_or_none()


def serialize_proposal(row: ResumePatchProposal) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "resume_id": str(row.resume_id),
        "target_job_id": str(row.target_job_id),
        "issue_id": str(row.issue_id),
        "strategy_id": str(row.strategy_id),
        "field_path": row.field_path,
        "before_text": row.before_text,
        "after_text": row.after_text,
        "suggested_text": row.after_text,
        "atomic_changes": row.atomic_changes or [],
        "source_claim_ids": row.source_claim_ids or [],
        "source_evidence_ids": row.source_evidence_ids or [],
        "source_answer_ids": row.source_answer_ids or [],
        "fidelity_result": row.fidelity_result or {},
        "fidelity_status": "blocked" if (row.fidelity_result or {}).get("violated") else "ready",
        "status": row.status,
        "applied_resume_version_id": (
            str(row.applied_resume_version_id) if row.applied_resume_version_id else None
        ),
    }


async def confirm_proposal_facts(
    db: AsyncSession, proposal: ResumePatchProposal
) -> ResumePatchProposal:
    if proposal.status != "needs_confirmation":
        raise RuntimeError("proposal_not_confirmable")
    if (proposal.fidelity_result or {}).get("violated"):
        raise PermissionError("fidelity_blocked")
    proposal.status = "ready"
    await db.flush()
    return proposal


async def apply_proposal(
    db: AsyncSession, proposal: ResumePatchProposal, *, user_id: str
) -> ResumeVersion:
    if proposal.status != "ready":
        raise RuntimeError("proposal_not_ready")
    resume = await db.get(Resume, str(proposal.resume_id))
    if not resume or str(resume.user_id) != str(user_id):
        raise PermissionError("resume_not_owned")
    current_before = value_at_field_path(resume.parsed_json or {}, proposal.field_path)
    if current_before != proposal.before_text:
        proposal.status = "expired"
        raise RuntimeError("proposal_stale")
    claims = (
        (
            await db.execute(
                select(ResumeClaim).where(
                    ResumeClaim.id.in_(proposal.source_claim_ids or ["__none__"]),
                    ResumeClaim.user_id == str(user_id),
                    ResumeClaim.workflow_state != "withdrawn",
                )
            )
        )
        .scalars()
        .all()
    )
    if {str(row.id) for row in claims} != set(proposal.source_claim_ids or []):
        raise PermissionError("candidate_source_required")
    source_corpus = "；".join(
        value for value in [proposal.before_text, *(row.current_text for row in claims)] if value
    )
    fidelity = assess_fidelity(source_corpus, proposal.after_text)
    proposal.fidelity_result = fidelity
    if fidelity.get("violated"):
        proposal.status = "expired"
        raise PermissionError("fidelity_blocked")

    updated = apply_field_path(
        deepcopy(resume.parsed_json or {}),
        proposal.field_path,
        proposal.after_text,
    )
    resume.parsed_json = updated
    await db.flush()
    version = await create_resume_version(
        db,
        resume,
        user_id=str(user_id),
        reason="target_job_patch",
        actor_id=str(user_id),
    )
    version.parent_version_id = str(proposal.resume_version_id)
    proposal.status = "applied"
    proposal.applied_at = now_utc()
    proposal.applied_resume_version_id = str(version.id)
    issue = await db.get(OptimizationIssue, str(proposal.issue_id))
    if issue:
        issue.status = "resolved"
    await db.flush()
    return version


async def update_action_status(
    db: AsyncSession,
    *,
    action: ReadinessAction,
    status: str,
    completion_evidence_id: str | None,
    user_id: str,
) -> ReadinessAction:
    if status not in {"planned", "in_progress", "completed", "abandoned"}:
        raise ValueError("invalid_action_status")
    if completion_evidence_id:
        artifact = await db.get(EvidenceArtifact, str(completion_evidence_id))
        if not artifact or str(artifact.user_id) != str(user_id) or artifact.withdrawn_at:
            raise PermissionError("evidence_not_owned")
        action.completion_evidence_id = str(artifact.id)
    action.status = status
    action.completed_at = now_utc() if status == "completed" else None
    await db.flush()
    return action
