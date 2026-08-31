"""PR15 employer screening APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .api_idempotency import idempotent_write
from .application_routes import (
    ClarificationRequest,
    _notify_clarification_requested,
    _send_clarification_for_application,
)
from .database import get_db
from .models_db import JobApplication, User
from .screening import (
    add_screening_rules,
    create_screening_run,
    execute_screening_run,
    get_result_for_employer,
    list_results_page,
    mark_result_reviewed,
    mark_results_reviewed,
    serialize_result,
    serialize_run,
    _run_for_employer,
)
from .security import require_employer

router = APIRouter(prefix="/employer", tags=["Employer Screening"])


class ScreeningRuleBody(BaseModel):
    rule_type: str
    field: str
    operator: str
    value: Any = None
    job_requirement_id: str | None = None
    employer_confirmed: bool = False
    legal_basis_note: str | None = None
    order_no: int | None = None
    enabled: bool = True


class ScreeningRulesBody(BaseModel):
    rules: list[ScreeningRuleBody] = Field(default_factory=list, min_length=1)


class ScreeningClarificationBody(BaseModel):
    claim_id: str | None = None
    claim_text: str = Field(..., min_length=1)
    questions: list[str] = Field(default_factory=list)
    evidence_suggestions: list[str] = Field(default_factory=list)


class BulkReviewBody(BaseModel):
    result_ids: list[str] = Field(min_length=1, max_length=100)


def _http_from_domain(exc: ValueError) -> HTTPException:
    code = str(exc)
    if code == "not_found":
        return HTTPException(status_code=404, detail="资源不存在或无权访问")
    mapping = {
        "sensitive_rule_rejected": (422, "规则包含敏感或歧视性条件"),
        "prohibited_education_proxy_rule": (
            422,
            "GPA 或院校声望不得作为关键词筛选代理",
        ),
        "illegal_hard_field": (422, "硬条件 field 不在白名单"),
        "illegal_hard_operator": (422, "硬条件 operator 不在白名单"),
        "hard_rule_requires_employer_confirmed": (422, "硬条件必须 employer_confirmed"),
        "hard_rule_requires_job_requirement": (422, "硬条件必须关联已确认 JobRequirement"),
        "hard_rule_requires_legal_basis_note": (422, "硬条件必须填写 legal_basis_note"),
        "job_requirement_not_confirmed": (422, "JobRequirement 未确认或不属于本 run 快照"),
        "hard_field_requirement_mismatch": (422, "硬条件 field 与 JobRequirement 类型不匹配"),
        "hard_requirement_value_unusable": (422, "该岗位要求无法生成可复核的硬条件值"),
        "illegal_keyword_field": (422, "关键词 field 不在白名单"),
        "illegal_keyword_operator": (422, "关键词 operator 不在白名单"),
        "keyword_value_required": (422, "关键词值不能为空"),
        "illegal_taxonomy_field": (422, "taxonomy field 不在白名单"),
        "illegal_taxonomy_operator": (422, "taxonomy operator 不在白名单"),
        "taxonomy_value_required": (422, "taxonomy 值不能为空"),
        "illegal_rule_type": (422, "不支持的 rule_type"),
        "run_not_configurable": (409, "当前批筛状态不可再配置规则"),
        "rules_required": (422, "请先配置至少一条规则"),
        "profile_snapshot_mismatch": (409, "岗位画像快照已变更，请新建批筛"),
        "result_ids_required": (422, "请选择至少一位候选人"),
    }
    status, detail = mapping.get(code, (400, code))
    return HTTPException(status_code=status, detail=detail)


@router.post("/jobs/{job_id}/screening-runs")
async def create_run(
    job_id: str,
    current_user: User = Depends(require_employer),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope=f"pr15.screening.create.{job_id}",
        idempotency_key=idempotency_key,
        request_payload={"job_id": job_id},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        try:
            run = await create_screening_run(
                db,
                employer_id=str(current_user.id),
                job_id=job_id,
            )
            payload = await serialize_run(db, run)
        except ValueError as exc:
            raise _http_from_domain(exc) from exc
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.post("/screening-runs/{run_id}/rules")
async def configure_rules(
    run_id: str,
    body: ScreeningRulesBody,
    current_user: User = Depends(require_employer),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope=f"pr15.screening.rules.{run_id}",
        idempotency_key=idempotency_key,
        request_payload=body.model_dump(),
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        try:
            await add_screening_rules(
                db,
                employer_id=str(current_user.id),
                run_id=run_id,
                rules=[item.model_dump() for item in body.rules],
            )
            run = await _run_for_employer(
                db,
                run_id=run_id,
                employer_id=str(current_user.id),
            )
            payload = await serialize_run(db, run)
        except ValueError as exc:
            raise _http_from_domain(exc) from exc
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.post("/screening-runs/{run_id}/execute")
async def execute_run(
    run_id: str,
    current_user: User = Depends(require_employer),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope=f"pr15.screening.execute.{run_id}",
        idempotency_key=idempotency_key,
        request_payload={"run_id": run_id},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        try:
            payload = await execute_screening_run(
                db,
                employer_id=str(current_user.id),
                run_id=run_id,
            )
        except ValueError as exc:
            raise _http_from_domain(exc) from exc
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.get("/screening-runs/{run_id}")
async def get_run(
    run_id: str,
    current_user: User = Depends(require_employer),
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await _run_for_employer(
            db,
            run_id=run_id,
            employer_id=str(current_user.id),
        )
        return await serialize_run(db, run)
    except ValueError as exc:
        raise _http_from_domain(exc) from exc


@router.get("/screening-runs/{run_id}/results")
async def get_results(
    run_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    hard_status: str | None = Query(None, pattern="^(pass|fail|unknown)$"),
    review_status: str | None = Query(
        None,
        pattern="^(pending_review|reviewed|clarification_requested)$",
    ),
    current_user: User = Depends(require_employer),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_results_page(
            db,
            employer_id=str(current_user.id),
            run_id=run_id,
            limit=limit,
            offset=offset,
            hard_status=hard_status,
            review_status=review_status,
        )
    except ValueError as exc:
        raise _http_from_domain(exc) from exc


@router.post("/screening-runs/{run_id}/results/mark-reviewed")
async def bulk_mark_reviewed(
    run_id: str,
    body: BulkReviewBody,
    current_user: User = Depends(require_employer),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope=f"pr15.screening.bulk_review.{run_id}",
        idempotency_key=idempotency_key,
        request_payload=body.model_dump(),
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        try:
            rows = await mark_results_reviewed(
                db,
                employer_id=str(current_user.id),
                run_id=run_id,
                result_ids=body.result_ids,
            )
        except ValueError as exc:
            raise _http_from_domain(exc) from exc
        payload = {"updated": len(rows), "result_ids": [str(row.id) for row in rows]}
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.get("/screening-results/{result_id}")
async def get_result(
    result_id: str,
    current_user: User = Depends(require_employer),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await get_result_for_employer(
            db,
            employer_id=str(current_user.id),
            result_id=result_id,
        )
        return await serialize_result(db, result, include_trace=True)
    except ValueError as exc:
        raise _http_from_domain(exc) from exc


@router.post("/screening-results/{result_id}/mark-reviewed")
async def mark_reviewed(
    result_id: str,
    current_user: User = Depends(require_employer),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope=f"pr15.screening.review.{result_id}",
        idempotency_key=idempotency_key,
        request_payload={"result_id": result_id},
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        try:
            result = await mark_result_reviewed(
                db,
                employer_id=str(current_user.id),
                result_id=result_id,
            )
            payload = await serialize_result(db, result, include_trace=True)
        except ValueError as exc:
            raise _http_from_domain(exc) from exc
        gate.set_response(200, payload)
        await db.commit()
        return payload


@router.post("/screening-results/{result_id}/clarification")
async def request_clarification(
    result_id: str,
    body: ScreeningClarificationBody,
    current_user: User = Depends(require_employer),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Reuse existing clarification domain service; never creates authorization."""
    async with idempotent_write(
        db,
        user_id=str(current_user.id),
        scope=f"pr15.screening.clarify.{result_id}",
        idempotency_key=idempotency_key,
        request_payload=body.model_dump(),
    ) as gate:
        if gate.replay is not None:
            return gate.replay
        try:
            result = await get_result_for_employer(
                db,
                employer_id=str(current_user.id),
                result_id=result_id,
            )
        except ValueError as exc:
            raise _http_from_domain(exc) from exc

        application = await db.get(JobApplication, str(result.application_id))
        if not application:
            raise HTTPException(status_code=404, detail="资源不存在或无权访问")

        # Reuse the domain service in the same transaction as result status and
        # the idempotency ledger. It never creates a new authorization relation.
        clarification = await _send_clarification_for_application(
            db,
            application,
            current_user,
            ClarificationRequest(
                claim_id=body.claim_id,
                claim_text=body.claim_text,
                questions=body.questions,
                evidence_suggestions=body.evidence_suggestions,
            ),
            commit=False,
            notify=False,
        )
        result = await get_result_for_employer(
            db,
            employer_id=str(current_user.id),
            result_id=result_id,
        )
        result.status = "clarification_requested"
        payload = {
            "result": await serialize_result(db, result, include_trace=True),
            "clarification": clarification,
        }
        gate.set_response(200, payload)
        await db.commit()
        await _notify_clarification_requested(
            db,
            application=application,
            employer=current_user,
            message_id=str(clarification["message"]["id"]),
            claim_id=body.claim_id,
        )
        return payload
