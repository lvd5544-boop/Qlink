from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from .auth import get_current_user
from .database import get_db
from .matching_hybrid import full_match_evaluation
from .models_db import ApplicationMessage, JobApplication, JobDescription, Resume, User

router = APIRouter(prefix="/applications", tags=["岗位申请"])

class ApplyRequest(BaseModel):
    job_id: str
    resume_id: str
    cover_letter: Optional[str] = None

class MessageRequest(BaseModel):
    body: str

def _application_payload(app: JobApplication, job: JobDescription | None = None):
    return {
        "id": str(app.id),
        "job_id": app.job_id,
        "job_title": job.title if job else "",
        "employer_id": app.employer_id,
        "candidate_id": app.candidate_id,
        "resume_id": app.resume_id,
        "status": app.status,
        "cover_letter": app.cover_letter,
        "created_at": app.created_at.isoformat() if app.created_at else None,
        "updated_at": app.updated_at.isoformat() if app.updated_at else None,
    }

async def _ensure_participant(app: JobApplication, user: User):
    user_id = str(user.id)
    if user_id not in {app.candidate_id, app.employer_id}:
        raise HTTPException(status_code=403, detail="无权查看该申请")

@router.post("")
async def apply_job(
    req: ApplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "candidate":
        raise HTTPException(status_code=403, detail="仅求职者可申请岗位")

    job = await db.get(JobDescription, req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")

    resume = await db.get(Resume, req.resume_id)
    if not resume or resume.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="简历不存在或不属于当前用户")

    existing = await db.execute(
        select(JobApplication).where(
            JobApplication.job_id == req.job_id,
            JobApplication.candidate_id == str(current_user.id),
        )
    )
    existing_app = existing.scalars().first()
    if existing_app:
        return {
            "status": "exists",
            "application": _application_payload(existing_app, job),
        }

    application = JobApplication(
        job_id=req.job_id,
        employer_id=job.employer_id,
        candidate_id=str(current_user.id),
        resume_id=req.resume_id,
        cover_letter=req.cover_letter,
    )
    db.add(application)
    await db.flush()

    if req.cover_letter:
        db.add(
            ApplicationMessage(
                application_id=str(application.id),
                sender_id=str(current_user.id),
                body=req.cover_letter,
            )
        )

    await db.commit()
    await db.refresh(application)
    return {
        "status": "ok",
        "application": _application_payload(application, job),
    }

@router.get("/mine")
async def my_applications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(JobApplication).where(
        JobApplication.candidate_id == str(current_user.id)
    ).order_by(JobApplication.created_at.desc())
    result = await db.execute(stmt)
    applications = result.scalars().all()

    payload = []
    for app in applications:
        job = await db.get(JobDescription, app.job_id)
        payload.append(_application_payload(app, job))
    return payload

@router.get("/mine/evaluations")
async def my_applications_with_evaluations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """已申请岗位 + v2 十维评分与职业建议。"""
    if current_user.role != "candidate":
        raise HTTPException(status_code=403, detail="仅求职者可查看")

    stmt = select(JobApplication).where(
        JobApplication.candidate_id == str(current_user.id)
    ).order_by(JobApplication.created_at.desc())
    result = await db.execute(stmt)
    applications = result.scalars().all()

    payload = []
    for app in applications:
        job = await db.get(JobDescription, app.job_id)
        resume = await db.get(Resume, app.resume_id)
        base = _application_payload(app, job)
        evaluation = None
        if job and resume and resume.parsed_json:
            evaluation = full_match_evaluation(
                resume.parsed_json,
                job.parsed_json or {},
                job_title=job.title,
            )
        payload.append({
            **base,
            "job_location": (job.parsed_json or {}).get("location") if job else None,
            "job_salary": (job.parsed_json or {}).get("salary_range") if job else None,
            "evaluation": evaluation,
        })
    return payload

@router.get("/job/{job_id}")
async def job_applications(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可查看岗位申请")

    job = await db.get(JobDescription, job_id)
    if not job or job.employer_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="岗位不存在或无权查看")

    stmt = select(JobApplication).where(
        JobApplication.job_id == job_id
    ).order_by(JobApplication.created_at.desc())
    result = await db.execute(stmt)
    applications = result.scalars().all()

    payload = []
    for app in applications:
        resume = await db.get(Resume, app.resume_id)
        parsed = resume.parsed_json if resume else {}
        payload.append({
            **_application_payload(app, job),
            "candidate_name": parsed.get("name") or "匿名候选人",
            "expected_title": parsed.get("expected_job_title") or "未填写",
            "resume_uploaded_at": resume.uploaded_at.isoformat() if resume and resume.uploaded_at else None,
        })
    return payload

@router.get("/{application_id}/messages")
async def application_messages(
    application_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    app = await db.get(JobApplication, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="申请不存在")
    await _ensure_participant(app, current_user)

    stmt = select(ApplicationMessage).where(
        ApplicationMessage.application_id == application_id
    ).order_by(ApplicationMessage.created_at.asc())
    result = await db.execute(stmt)
    messages = result.scalars().all()

    return [
        {
            "id": str(msg.id),
            "application_id": msg.application_id,
            "sender_id": msg.sender_id,
            "body": msg.body,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
            "is_mine": msg.sender_id == str(current_user.id),
        }
        for msg in messages
    ]

@router.post("/{application_id}/messages")
async def send_application_message(
    application_id: str,
    req: MessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    body = req.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="消息不能为空")

    app = await db.get(JobApplication, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="申请不存在")
    await _ensure_participant(app, current_user)

    msg = ApplicationMessage(
        application_id=application_id,
        sender_id=str(current_user.id),
        body=body,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return {
        "id": str(msg.id),
        "application_id": msg.application_id,
        "sender_id": msg.sender_id,
        "body": msg.body,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "is_mine": True,
    }
