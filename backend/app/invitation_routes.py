from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional
from .database import get_db
from .models_db import InterviewInvitation, User, Resume, JobDescription
from .auth import get_current_user
from .email_service import send_email

router = APIRouter(prefix="/invitations", tags=["面试邀请"])

class InviteRequest(BaseModel):
    job_id: str
    resume_id: str
    message: Optional[str] = None
    proposed_time: Optional[str] = None

@router.post("/send")
async def send_invitation(
    req: InviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可发送邀请")

    # 确认岗位存在且属于当前雇主
    job = await db.get(JobDescription, req.job_id)
    if not job or job.employer_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="岗位不存在或无权操作")

    # 确认简历存在且找到对应的求职者
    resume = await db.get(Resume, req.resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    candidate_id = resume.user_id

    # 避免重复邀请（pending 状态）
    existing = await db.execute(
        select(InterviewInvitation).where(
            InterviewInvitation.job_id == req.job_id,
            InterviewInvitation.resume_id == req.resume_id,
            InterviewInvitation.status == "pending"
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="已对该候选人发送过待处理的邀请")

    invitation = InterviewInvitation(
        job_id=req.job_id,
        employer_id=str(current_user.id),
        candidate_id=candidate_id,
        resume_id=req.resume_id,
        message=req.message,
        proposed_time=req.proposed_time,
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    # 发送邮件通知求职者（简化，异步）
    try:
        candidate_user = await db.get(User, candidate_id)
        to_email = candidate_user.email if candidate_user else f"{candidate_id}@example.com"
        html = f"<h3>您收到一封面试邀请</h3><p>岗位：{job.title}</p><p>消息：{req.message or '无'}</p><p>建议时间：{req.proposed_time or '未指定'}</p><p>请登录平台查看详情</p>"
        await send_email(to_email, "面试邀请", html)
    except Exception:
        pass  # 邮件失败不影响主流程

    return {"status": "ok", "invitation_id": str(invitation.id)}

@router.get("/received")
async def get_received_invitations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.role != "candidate":
        raise HTTPException(status_code=403, detail="仅求职者可查看")

    stmt = select(InterviewInvitation).where(
        InterviewInvitation.candidate_id == str(current_user.id)
    ).order_by(InterviewInvitation.created_at.desc())
    result = await db.execute(stmt)
    invitations = result.scalars().all()

    return [
        {
            "id": str(inv.id),
            "job_id": inv.job_id,
            "job_title": (await db.get(JobDescription, inv.job_id)).title if inv.job_id else "",
            "employer_id": inv.employer_id,
            "message": inv.message,
            "proposed_time": inv.proposed_time,
            "status": inv.status,
            "created_at": inv.created_at.isoformat()
        }
        for inv in invitations
    ]

@router.get("/sent")
async def get_sent_invitations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可查看")

    stmt = select(InterviewInvitation).where(
        InterviewInvitation.employer_id == str(current_user.id)
    ).order_by(InterviewInvitation.created_at.desc())
    result = await db.execute(stmt)
    invitations = result.scalars().all()

    return [
        {
            "id": str(inv.id),
            "job_id": inv.job_id,
            "candidate_id": inv.candidate_id,
            "resume_id": inv.resume_id,
            "status": inv.status,
            "created_at": inv.created_at.isoformat()
        }
        for inv in invitations
    ]

@router.put("/{invitation_id}/accept")
async def accept_invitation(
    invitation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    inv = await db.get(InterviewInvitation, invitation_id)
    if not inv or inv.candidate_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="邀请不存在")
    if inv.status != "pending":
        raise HTTPException(status_code=400, detail="邀请已处理")

    inv.status = "accepted"
    await db.commit()

    # 通知招聘方（邮件）
    try:
        employer_email = (await db.get(User, inv.employer_id)).email
        job_title = (await db.get(JobDescription, inv.job_id)).title
        html = f"<h3>候选人已接受面试邀请</h3><p>岗位：{job_title}</p><p>请登录平台查看</p>"
        await send_email(employer_email, "面试邀请已接受", html)
    except:
        pass

    return {"status": "ok", "message": "已接受邀请"}

@router.put("/{invitation_id}/decline")
async def decline_invitation(
    invitation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    inv = await db.get(InterviewInvitation, invitation_id)
    if not inv or inv.candidate_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="邀请不存在")
    if inv.status != "pending":
        raise HTTPException(status_code=400, detail="邀请已处理")

    inv.status = "declined"
    await db.commit()
    return {"status": "ok", "message": "已拒绝邀请"}