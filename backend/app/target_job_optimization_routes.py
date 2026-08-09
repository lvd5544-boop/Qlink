"""Candidate-only PR13 target-job optimization API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .api_idempotency import idempotent_write
from .database import get_db
from .models_db import OptimizationIssue, ReadinessAction, User
from .security import require_candidate
from .target_job_optimization import (
    apply_proposal,
    confirm_proposal_facts,
    create_rewrite_preview,
    generate_diagnostic,
    owned_issue,
    owned_proposal,
    select_strategy,
    serialize_diagnostic,
    serialize_proposal,
    update_action_status,
)

router = APIRouter(tags=["Target Job Optimization"])


class StrategyBody(BaseModel):
    strategy_id: str


class ActionStatusBody(BaseModel):
    status: str
    completion_evidence_id: str | None = None


def _error(exc: Exception) -> HTTPException:
    mapping = {
        "resume_not_owned": (404, "简历不存在或无权访问"),
        "job_not_found": (404, "岗位不存在"),
        "diagnostic_not_found": (404, "诊断不存在或无权访问"),
        "issue_not_found": (404, "诊断问题不存在或无权访问"),
        "strategy_not_in_issue": (422, "策略不属于该诊断问题"),
        "candidate_source_required": (
            409,
            "当前没有候选人 Claim/Evidence 来源，不能生成岗位定制改写",
        ),
        "proposal_not_found": (404, "改写提案不存在或无权访问"),
        "proposal_not_confirmable": (409, "改写提案当前不能确认"),
        "proposal_not_ready": (409, "请先逐条确认事实后再应用"),
        "proposal_stale": (409, "简历已变化，提案已过期，请重新诊断"),
        "fidelity_blocked": (409, "Fidelity 校验未通过，禁止应用"),
        "invalid_action_status": (422, "行动状态无效"),
        "evidence_not_owned": (404, "完成证据不存在或无权使用"),
    }
    status, detail = mapping.get(str(exc), (400, str(exc)))
    return HTTPException(status_code=status, detail=detail)


@router.post("/resumes/{resume_id}/jobs/{job_id}/diagnostics")
async def create_diagnostic(
    resume_id: str,
    job_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = str(current_user.id)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope="pr13.diagnostic.create",
        idempotency_key=idempotency_key,
        request_payload={"resume_id": resume_id, "job_id": job_id},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        try:
            diagnostic_id = await generate_diagnostic(
                db, user_id=user_id, resume_id=resume_id, job_id=job_id
            )
            payload = await serialize_diagnostic(
                db, user_id=user_id, job_id=job_id, diagnostic_id=diagnostic_id
            )
        except (ValueError, PermissionError, LookupError, RuntimeError) as exc:
            raise _error(exc) from exc
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.get("/resumes/{resume_id}/jobs/{job_id}/diagnostics/{diagnostic_id}")
async def get_diagnostic(
    resume_id: str,
    job_id: str,
    diagnostic_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = await serialize_diagnostic(
            db, user_id=str(current_user.id), job_id=job_id, diagnostic_id=diagnostic_id
        )
    except LookupError as exc:
        raise _error(exc) from exc
    if payload["resume_id"] != str(resume_id):
        raise HTTPException(status_code=404, detail="诊断不存在或无权访问")
    return payload


@router.post("/optimization/issues/{issue_id}/select-strategy")
async def choose_strategy(
    issue_id: str,
    body: StrategyBody,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = str(current_user.id)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope=f"pr13.issue.{issue_id}.strategy",
        idempotency_key=idempotency_key,
        request_payload=body.model_dump(),
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        issue = await owned_issue(db, issue_id=issue_id, user_id=user_id)
        if not issue:
            raise _error(LookupError("issue_not_found"))
        try:
            action = await select_strategy(
                db, issue=issue, strategy_id=body.strategy_id, user_id=user_id
            )
        except (ValueError, PermissionError) as exc:
            raise _error(exc) from exc
        payload = {
            "selected": True,
            "action": {
                "id": str(action.id),
                "title": action.title,
                "description": action.description,
                "status": action.status,
                "expected_time_horizon": action.expected_time_horizon,
                "user_cost": action.user_cost,
            },
        }
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.post("/optimization/issues/{issue_id}/rewrite-preview")
async def rewrite_preview(
    issue_id: str,
    body: StrategyBody,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = str(current_user.id)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope=f"pr13.issue.{issue_id}.rewrite",
        idempotency_key=idempotency_key,
        request_payload=body.model_dump(),
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        issue = await owned_issue(db, issue_id=issue_id, user_id=user_id)
        if not issue:
            raise _error(LookupError("issue_not_found"))
        try:
            proposal = await create_rewrite_preview(
                db, issue=issue, strategy_id=body.strategy_id, user_id=user_id
            )
        except (ValueError, PermissionError) as exc:
            raise _error(exc) from exc
        payload = {
            "observation": "看到你已有可追溯的候选人 Claim；以下文本只重组这些事实。",
            "job_connection": (
                f"对应目标岗位要求：{issue.target_requirement_id}"
                if issue.target_requirement_id
                else "用于提升目标岗位相关表达。"
            ),
            **serialize_proposal(proposal),
        }
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.post("/resume-patches/{proposal_id}/confirm-facts")
async def confirm_facts(
    proposal_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = str(current_user.id)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope=f"pr13.patch.{proposal_id}.confirm",
        idempotency_key=idempotency_key,
        request_payload={"proposal_id": proposal_id},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        proposal = await owned_proposal(db, proposal_id=proposal_id, user_id=user_id)
        if not proposal:
            raise _error(LookupError("proposal_not_found"))
        try:
            proposal = await confirm_proposal_facts(db, proposal)
        except (RuntimeError, PermissionError) as exc:
            raise _error(exc) from exc
        payload = serialize_proposal(proposal)
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.post("/resume-patches/{proposal_id}/apply")
async def apply_patch_proposal(
    proposal_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = str(current_user.id)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope=f"pr13.patch.{proposal_id}.apply",
        idempotency_key=idempotency_key,
        request_payload={"proposal_id": proposal_id},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        proposal = await owned_proposal(db, proposal_id=proposal_id, user_id=user_id)
        if not proposal:
            raise _error(LookupError("proposal_not_found"))
        try:
            version = await apply_proposal(db, proposal, user_id=user_id)
        except (RuntimeError, PermissionError, ValueError) as exc:
            raise _error(exc) from exc
        payload = {
            **serialize_proposal(proposal),
            "resume_version": {
                "id": str(version.id),
                "version_number": version.version_number,
                "parent_version_id": version.parent_version_id,
                "content_hash": version.content_hash,
            },
        }
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.post("/resume-patches/{proposal_id}/reject")
async def reject_patch_proposal(
    proposal_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = str(current_user.id)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope=f"pr13.patch.{proposal_id}.reject",
        idempotency_key=idempotency_key,
        request_payload={"proposal_id": proposal_id},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        proposal = await owned_proposal(db, proposal_id=proposal_id, user_id=user_id)
        if not proposal:
            raise _error(LookupError("proposal_not_found"))
        if proposal.status == "applied":
            raise HTTPException(status_code=409, detail="已应用的提案不能拒绝")
        proposal.status = "rejected"
        payload = serialize_proposal(proposal)
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.get("/resume-patches/{proposal_id}/fidelity")
async def get_patch_fidelity(
    proposal_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    proposal = await owned_proposal(db, proposal_id=proposal_id, user_id=str(current_user.id))
    if not proposal:
        raise _error(LookupError("proposal_not_found"))
    return {
        "proposal_id": str(proposal.id),
        "fidelity_result": proposal.fidelity_result or {},
        "source_claim_ids": proposal.source_claim_ids or [],
        "source_evidence_ids": proposal.source_evidence_ids or [],
    }


@router.post("/advisor/jobs/{job_id}/actions/{action_id}/status")
async def set_action_status(
    job_id: str,
    action_id: str,
    body: ActionStatusBody,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    user_id = str(current_user.id)
    async with idempotent_write(
        db,
        user_id=user_id,
        scope=f"pr13.action.{action_id}.status",
        idempotency_key=idempotency_key,
        request_payload={"job_id": job_id, **body.model_dump()},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        action = (
            await db.execute(
                select(ReadinessAction).where(
                    ReadinessAction.id == str(action_id),
                    ReadinessAction.user_id == user_id,
                    ReadinessAction.job_id == str(job_id),
                )
            )
        ).scalar_one_or_none()
        if not action:
            raise HTTPException(status_code=404, detail="行动不存在或无权访问")
        try:
            action = await update_action_status(
                db,
                action=action,
                status=body.status,
                completion_evidence_id=body.completion_evidence_id,
                user_id=user_id,
            )
        except (ValueError, PermissionError) as exc:
            raise _error(exc) from exc
        payload = {
            "id": str(action.id),
            "status": action.status,
            "completion_evidence_id": action.completion_evidence_id,
            "current_readiness_changed": False,
            "notice": "行动状态不会直接提高当前准备度；需新增并确认 Claim/Evidence 后重新诊断。",
        }
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.get("/advisor/jobs/{job_id}/readiness")
async def get_job_readiness(
    job_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    latest = (
        await db.execute(
            select(OptimizationIssue)
            .where(
                OptimizationIssue.user_id == str(current_user.id),
                OptimizationIssue.job_id == str(job_id),
                OptimizationIssue.status != "superseded",
            )
            .order_by(OptimizationIssue.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not latest:
        raise HTTPException(status_code=404, detail="请先针对该岗位生成简历诊断")
    payload = await serialize_diagnostic(
        db,
        user_id=str(current_user.id),
        job_id=job_id,
        diagnostic_id=str(latest.diagnostic_id),
    )
    return payload["readiness"]
