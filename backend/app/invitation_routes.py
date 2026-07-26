from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from .database import get_db
from .models_db import (
    InterviewInvitation,
    User,
    Resume,
    JobDescription,
    JobApplication,
    ApplicationMessage,
)
from .auth import get_current_user
from .email_service import send_email
from .application_events import event_bus
from .application_state import (
    ResumeImmutableError,
    ensure_resume_unchanged,
    set_application_status,
)
from .application_authz import ensure_application_has_candidate_authorization
from .claim_threads import claim_threads_summary

router = APIRouter(prefix="/invitations", tags=["面试邀请"])


class InviteRequest(BaseModel):
    job_id: str
    resume_id: str
    message: Optional[str] = None
    proposed_time: Optional[str] = None
    application_id: Optional[str] = None
    idempotency_key: Optional[str] = None


async def _get_or_create_application(
    db: AsyncSession,
    *,
    job: JobDescription,
    resume: Resume,
    application_id: Optional[str] = None,
) -> JobApplication:
    if application_id:
        result = await db.execute(
            select(JobApplication).where(JobApplication.id == application_id).with_for_update()
        )
        app = result.scalars().first()
        if not app:
            raise HTTPException(status_code=404, detail="资源不存在或无权访问")
        if (
            app.job_id != str(job.id)
            or app.employer_id != str(job.employer_id)
            or app.candidate_id != str(resume.user_id)
        ):
            raise HTTPException(status_code=404, detail="资源不存在或无权访问")
        ensure_resume_unchanged(app, str(resume.id))
        ensure_application_has_candidate_authorization(app)
        return app

    stmt = (
        select(JobApplication)
        .where(
            JobApplication.job_id == str(job.id),
            JobApplication.candidate_id == resume.user_id,
            JobApplication.employer_id == str(job.employer_id),
        )
        .order_by(JobApplication.created_at.desc())
        .with_for_update()
    )
    result = await db.execute(stmt)
    app = result.scalars().first()
    if app:
        ensure_resume_unchanged(app, str(resume.id))
        ensure_application_has_candidate_authorization(app)
        return app
    raise HTTPException(status_code=404, detail="资源不存在或无权访问")


@router.post("/send")
async def send_invitation(
    req: InviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可发送邀请")

    job = await db.get(JobDescription, req.job_id)
    if not job or job.employer_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="岗位不存在或无权操作")

    resume = await db.get(Resume, req.resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="资源不存在或无权访问")
    candidate_id = resume.user_id

    try:
        application = await _get_or_create_application(
            db,
            job=job,
            resume=resume,
            application_id=req.application_id,
        )
    except ResumeImmutableError as e:
        raise HTTPException(status_code=e.code, detail=str(e))

    existing = await db.execute(
        select(InterviewInvitation).where(
            InterviewInvitation.application_id == str(application.id),
            InterviewInvitation.status == "pending",
        )
    )
    existing_invitation = existing.scalars().first()
    if existing_invitation:
        return {
            "status": "exists",
            "invitation_id": str(existing_invitation.id),
            "application_id": str(application.id),
            "application_status": application.status,
        }

    if application.status in {"accepted", "rejected"}:
        raise HTTPException(status_code=409, detail="终态申请不能发送面试邀请")
    if claim_threads_summary(application).get("open_claim_count"):
        raise HTTPException(status_code=409, detail="仍有待回复 Claim，请先完成或关闭澄清")
    if application.status == "interview_invited":
        raise HTTPException(status_code=409, detail="该申请已经发送过面试邀请")

    set_application_status(
        application,
        "interview_invited",
        action="create_invitation",
        actor_role="employer",
        actor_id=str(current_user.id),
        source="interview_invitation",
        request_key=req.idempotency_key,
    )

    invitation = InterviewInvitation(
        job_id=req.job_id,
        employer_id=str(current_user.id),
        candidate_id=candidate_id,
        resume_id=req.resume_id,
        application_id=str(application.id),
        message=req.message,
        proposed_time=req.proposed_time,
    )
    db.add(invitation)
    try:
        await db.flush()

        # 写入申请时间线，两端可见
        invite_body = (
            f"[面试邀请]\n岗位：{job.title}\n"
            f"消息：{req.message or '无'}\n"
            f"建议时间：{req.proposed_time or '未指定'}"
        )
        db.add(
            ApplicationMessage(
                application_id=str(application.id),
                sender_id=str(current_user.id),
                body=invite_body,
                message_kind="interview_invite",
                message_meta={
                    "invitation_id": str(invitation.id),
                    "proposed_time": req.proposed_time,
                    "invitation_pending": True,
                    "idempotency_key": req.idempotency_key,
                },
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(invitation)

    await event_bus.publish(
        application_id=str(application.id),
        event_type="interview_invited",
        payload={
            "invitation_id": str(invitation.id),
            "job_title": job.title,
            "status": application.status,
        },
        candidate_id=candidate_id,
        employer_id=str(current_user.id),
    )

    try:
        candidate_user = await db.get(User, candidate_id)
        to_email = candidate_user.email if candidate_user and candidate_user.email else None
        if to_email:
            html = (
                f"<h3>您收到一封面试邀请</h3><p>岗位：{job.title}</p>"
                f"<p>消息：{req.message or '无'}</p>"
                f"<p>建议时间：{req.proposed_time or '未指定'}</p>"
                f"<p>请登录平台「已申请岗位」查看详情</p>"
            )
            await send_email(to_email, "面试邀请", html)
    except Exception:
        meta = dict(application.pipeline_meta or {})
        failures = list(meta.get("notification_failures") or [])
        failures.append(
            {
                "kind": "invitation_email",
                "invitation_id": str(invitation.id),
                "status": "failed",
            }
        )
        meta["notification_failures"] = failures[-20:]
        application.pipeline_meta = meta
        try:
            await db.commit()
        except Exception:
            await db.rollback()

    return {
        "status": "ok",
        "invitation_id": str(invitation.id),
        "application_id": str(application.id),
        "application_status": application.status,
    }


@router.get("/received")
async def get_received_invitations(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if current_user.role != "candidate":
        raise HTTPException(status_code=403, detail="仅求职者可查看")

    stmt = (
        select(InterviewInvitation)
        .where(InterviewInvitation.candidate_id == str(current_user.id))
        .order_by(InterviewInvitation.created_at.desc())
    )
    result = await db.execute(stmt)
    invitations = result.scalars().all()

    payload = []
    for inv in invitations:
        job = await db.get(JobDescription, inv.job_id) if inv.job_id else None
        payload.append(
            {
                "id": str(inv.id),
                "job_id": inv.job_id,
                "job_title": job.title if job else "",
                "employer_id": inv.employer_id,
                "application_id": inv.application_id,
                "resume_id": inv.resume_id,
                "message": inv.message,
                "proposed_time": inv.proposed_time,
                "status": inv.status,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
                "interview_ws_hint": {
                    "mode": "claim_followup",
                    "resume_id": inv.resume_id,
                    "application_id": inv.application_id,
                },
            }
        )
    return payload


@router.get("/sent")
async def get_sent_invitations(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可查看")

    stmt = (
        select(InterviewInvitation)
        .where(InterviewInvitation.employer_id == str(current_user.id))
        .order_by(InterviewInvitation.created_at.desc())
    )
    result = await db.execute(stmt)
    invitations = result.scalars().all()

    return [
        {
            "id": str(inv.id),
            "job_id": inv.job_id,
            "candidate_id": inv.candidate_id,
            "resume_id": inv.resume_id,
            "application_id": inv.application_id,
            "status": inv.status,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        }
        for inv in invitations
    ]


@router.put("/{invitation_id}/accept")
async def accept_invitation(
    invitation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    inv = await db.get(InterviewInvitation, invitation_id)
    if not inv or inv.candidate_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="邀请不存在")
    if inv.status != "pending":
        raise HTTPException(status_code=400, detail="邀请已处理")

    inv.status = "accepted"
    application = None
    if inv.application_id:
        application = await db.get(JobApplication, inv.application_id)
        if application and application.status not in {"accepted", "rejected"}:
            db.add(
                ApplicationMessage(
                    application_id=str(application.id),
                    sender_id=str(current_user.id),
                    body="[面试邀请] 候选人已接受面试邀请",
                    message_kind="interview_invite",
                    message_meta={"invitation_status": "accepted", "invitation_id": str(inv.id)},
                )
            )

    await db.commit()

    if application:
        await event_bus.publish(
            application_id=str(application.id),
            event_type="invitation_accepted",
            payload={"invitation_id": str(inv.id)},
            candidate_id=inv.candidate_id,
            employer_id=inv.employer_id,
        )

    try:
        employer = await db.get(User, inv.employer_id)
        job = await db.get(JobDescription, inv.job_id)
        if employer and employer.email and job:
            html = f"<h3>候选人已接受面试邀请</h3><p>岗位：{job.title}</p><p>请登录平台查看</p>"
            await send_email(employer.email, "面试邀请已接受", html)
    except Exception:
        pass

    return {
        "status": "ok",
        "message": "已接受邀请",
        "application_id": inv.application_id,
        "resume_id": inv.resume_id,
    }


@router.put("/{invitation_id}/decline")
async def decline_invitation(
    invitation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    inv = await db.get(InterviewInvitation, invitation_id)
    if not inv or inv.candidate_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="邀请不存在")
    if inv.status != "pending":
        raise HTTPException(status_code=400, detail="邀请已处理")

    inv.status = "declined"
    if inv.application_id:
        db.add(
            ApplicationMessage(
                application_id=inv.application_id,
                sender_id=str(current_user.id),
                body="[面试邀请] 候选人已拒绝面试邀请",
                message_kind="interview_invite",
                message_meta={"invitation_status": "declined", "invitation_id": str(inv.id)},
            )
        )
    await db.commit()
    return {"status": "ok", "message": "已拒绝邀请"}
