"""Candidate-only HTTP surface for PR9 improvement simulation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .claim_passport import sync_resume_claims
from .database import get_db
from .models_db import JobDescription, PotentialSimulationEvent, Resume, ResumeClaim, User
from .potential_simulation import RULE_VERSION, build_simulation
from .security import require_admin, require_candidate

router = APIRouter(tags=["Potential Simulation"])


class SimulationRequest(BaseModel):
    strategy_ids: list[str] = Field(default_factory=list, max_length=30)


class SimulationEventRequest(BaseModel):
    event_type: Literal["rejected", "adopted", "completed"]
    strategy_ids: list[str] = Field(default_factory=list, max_length=30)


def _pilot_metrics(events: list[PotentialSimulationEvent]) -> dict:
    """Aggregate only product counters; never expose candidate or employer data."""
    event_counts: dict[str, int] = {}
    strategy_counts: dict[str, int] = {}
    for event in events:
        event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1
        for strategy_id in event.strategy_ids or []:
            strategy = str(strategy_id).rsplit(":", 1)[-1]
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
    selected = event_counts.get("strategies_selected", 0)
    viewed = event_counts.get("viewed", 0)
    total_strategies = sum(strategy_counts.values())
    repeated = max(strategy_counts.values(), default=0)
    quantification = strategy_counts.get("quantification", 0)
    return {
        "sample_size": len(events),
        "event_counts": event_counts,
        "strategy_counts": strategy_counts,
        "view_to_selection_rate": round(selected / viewed, 4) if viewed else None,
        "selection_to_adoption_rate": round(event_counts.get("adopted", 0) / selected, 4)
        if selected
        else None,
        "selection_to_completion_rate": round(event_counts.get("completed", 0) / selected, 4)
        if selected
        else None,
        "quantification_strategy_ratio": round(quantification / total_strategies, 4)
        if total_strategies
        else None,
        "strategy_repetition_rate": round(repeated / total_strategies, 4)
        if total_strategies
        else None,
        "privacy_notice": "仅返回聚合计数；不含候选人、简历、岗位或敏感属性。",
        "interpretation_notice": "样本量不足或未完成人工抽检时，不得据此宣称校准或公平性结论。",
    }


async def _owned_inputs(db: AsyncSession, resume_id: str, job_id: str, user: User):
    resume = await db.get(Resume, resume_id)
    if not resume or resume.user_id != str(user.id):
        raise HTTPException(status_code=404, detail="简历不存在或无权访问")
    job = await db.get(JobDescription, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")
    await sync_resume_claims(db, resume, actor_id=str(user.id), reason="potential_simulation")
    claims = (
        (await db.execute(select(ResumeClaim).where(ResumeClaim.resume_id == str(resume.id))))
        .scalars()
        .all()
    )
    return (
        resume,
        job,
        [
            {
                "id": str(item.id),
                "current_text": item.current_text,
                "field_path": item.field_path,
                "evidence_state": item.evidence_state,
            }
            for item in claims
        ],
    )


async def _simulate(
    db: AsyncSession,
    resume_id: str,
    job_id: str,
    user: User,
    strategy_ids: list[str] | None,
):
    resume, job, claims = await _owned_inputs(db, resume_id, job_id, user)
    try:
        result = build_simulation(
            resume.parsed_json or {},
            {**(job.parsed_json or {}), "_raw_text": job.raw_text or ""},
            job.title or "",
            claims,
            strategy_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return resume, job, result


@router.get("/resumes/{resume_id}/jobs/{job_id}/improvement-simulation")
async def get_improvement_simulation(
    resume_id: str,
    job_id: str,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    resume, job, result = await _simulate(db, resume_id, job_id, current_user, None)
    db.add(
        PotentialSimulationEvent(
            resume_id=str(resume.id),
            job_id=str(job.id),
            user_id=str(current_user.id),
            event_type="viewed",
            strategy_ids=result["selected_strategy_ids"],
            result_snapshot=result,
            rule_version=RULE_VERSION,
        )
    )
    await db.commit()
    return result


@router.post("/resumes/{resume_id}/jobs/{job_id}/improvement-simulation")
async def select_improvement_strategies(
    resume_id: str,
    job_id: str,
    body: SimulationRequest,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    resume, job, result = await _simulate(db, resume_id, job_id, current_user, body.strategy_ids)
    db.add(
        PotentialSimulationEvent(
            resume_id=str(resume.id),
            job_id=str(job.id),
            user_id=str(current_user.id),
            event_type="strategies_selected",
            strategy_ids=result["selected_strategy_ids"],
            result_snapshot=result,
            rule_version=RULE_VERSION,
        )
    )
    await db.commit()
    return result


@router.post("/resumes/{resume_id}/jobs/{job_id}/improvement-simulation/events")
async def record_improvement_simulation_event(
    resume_id: str,
    job_id: str,
    body: SimulationEventRequest,
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    resume, job, result = await _simulate(db, resume_id, job_id, current_user, body.strategy_ids)
    db.add(
        PotentialSimulationEvent(
            resume_id=str(resume.id),
            job_id=str(job.id),
            user_id=str(current_user.id),
            event_type=body.event_type,
            strategy_ids=result["selected_strategy_ids"],
            result_snapshot=result,
            rule_version=RULE_VERSION,
        )
    )
    await db.commit()
    return {"event_type": body.event_type, "recorded": True}


@router.get("/admin/potential-simulation/pilot-metrics")
async def potential_simulation_pilot_metrics(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only, aggregate-only inputs for the PR9 pilot review protocol."""
    events = (
        (
            await db.execute(
                select(PotentialSimulationEvent).order_by(PotentialSimulationEvent.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return _pilot_metrics(events)
