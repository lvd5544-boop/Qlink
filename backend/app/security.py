"""Reusable authorization primitives for route-level RBAC and ownership checks."""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .models_db import JobDescription, Resume, User


def _require_role(user: User, allowed: Iterable[str]) -> User:
    roles = set(allowed)
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="无权执行该操作")
    return user


async def require_candidate(
    current_user: User = Depends(get_current_user),
) -> User:
    return _require_role(current_user, {"candidate"})


async def require_employer(
    current_user: User = Depends(get_current_user),
) -> User:
    return _require_role(current_user, {"employer"})


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    return _require_role(current_user, {"admin"})


async def require_candidate_or_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    return _require_role(current_user, {"candidate", "admin"})


async def owned_resume_or_404(db: AsyncSession, resume_id: str, user: User) -> Resume:
    resume = await db.get(Resume, resume_id)
    if not resume or (user.role != "admin" and str(resume.user_id) != str(user.id)):
        raise HTTPException(status_code=404, detail="资源不存在或无权访问")
    return resume


async def owned_job_or_404(db: AsyncSession, job_id: str, user: User) -> JobDescription:
    job = await db.get(JobDescription, job_id)
    if not job or (user.role != "admin" and str(job.employer_id) != str(user.id)):
        raise HTTPException(status_code=404, detail="资源不存在或无权访问")
    return job
