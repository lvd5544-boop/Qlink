"""Canonical Resume Coach application service shared by all HTTP entrypoints."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .billing_accounts import reserve_feature_entitlement
from .models_db import Resume, User
from .provider_costs import record_metering_cost_if_called
from .resume_coach import generate_resume_coach
from .resume_suggestion_store import (
    list_pending_suggestions,
    sync_suggestions_for_source,
)
from .resume_suggestions import build_coach_actionable_suggestions
from .usage_metering import finalize_quota


async def run_resume_coach(
    db: AsyncSession,
    *,
    actor: User,
    resume: Resume,
    company_id: str,
    role_family: str | None,
    target_job_title: str | None,
    idempotency_key: str | None,
    entrypoint: str,
) -> dict:
    request_payload = {
        "resume_id": str(resume.id),
        "company_id": company_id,
        "role_family": role_family,
        "target_job_title": target_job_title,
    }
    reservation = await reserve_feature_entitlement(
        db,
        actor=actor,
        feature="resume_coach",
        idempotency_key=idempotency_key or str(uuid.uuid4()),
        request_payload=request_payload,
        reservation_meta={"entrypoint": entrypoint},
    )
    if not reservation["created"]:
        raise HTTPException(
            status_code=409,
            detail={"error": "idempotency_replayed", **reservation},
        )

    try:
        result = await generate_resume_coach(
            db,
            resume.parsed_json or {},
            company_id,
            role_family,
            target_job_title,
        )
    except ValueError as exc:
        await finalize_quota(
            db,
            reservation["reservation_id"],
            succeeded=False,
            failure_reason="invalid_company",
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        await finalize_quota(
            db,
            reservation["reservation_id"],
            succeeded=False,
            failure_reason="model_error",
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "resume_coach_unavailable"},
        ) from exc

    metering = result.pop("_metering", {})
    try:
        coach_actionable = build_coach_actionable_suggestions(
            resume.parsed_json or {},
            result,
        )
        await sync_suggestions_for_source(
            db,
            str(resume.id),
            "coach",
            coach_actionable,
        )
        result["actionable_suggestions"] = coach_actionable
        result["pending_suggestions"] = await list_pending_suggestions(
            db,
            str(resume.id),
        )
        result["coach_suggestions_count"] = len(coach_actionable)
    except Exception:
        await db.rollback()
        await record_metering_cost_if_called(
            db,
            metering=metering,
            reservation_id=reservation["reservation_id"],
            user_id=str(actor.id),
            organization_id=None,
            feature="resume_coach",
            prompt_version="resume-coach-v1",
        )
        await finalize_quota(
            db,
            reservation["reservation_id"],
            succeeded=False,
            failure_reason="postprocess_error",
            meta={"model_called": bool(metering.get("model_called"))},
        )
        raise

    await record_metering_cost_if_called(
        db,
        metering=metering,
        reservation_id=reservation["reservation_id"],
        user_id=str(actor.id),
        organization_id=None,
        feature="resume_coach",
        prompt_version="resume-coach-v1",
    )
    model_output_used = bool(metering.get("model_output_used"))
    await finalize_quota(
        db,
        reservation["reservation_id"],
        succeeded=model_output_used,
        failure_reason=(
            None
            if model_output_used
            else (
                "no_model_call"
                if not metering.get("model_called")
                else "model_output_not_delivered"
            )
        ),
        meta={
            "model_called": bool(metering.get("model_called")),
            "suggestions_count": len(coach_actionable),
        },
    )
    # Metering-disabled mode has no reservation commit.
    await db.commit()
    return result
