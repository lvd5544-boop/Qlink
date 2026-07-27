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
from .security import require_candidate

router = APIRouter(tags=["Potential Simulation"])


class SimulationRequest(BaseModel):
    strategy_ids: list[str] = Field(default_factory=list, max_length=30)


class SimulationEventRequest(BaseModel):
    event_type: Literal["rejected", "adopted", "completed"]
    strategy_ids: list[str] = Field(default_factory=list, max_length=30)


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
            job.parsed_json or {},
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
