"""Transactional deletion policies for resumes, jobs, and accounts."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models_db import (
    ApplicationMessage,
    AuditFindingFeedback,
    CredibilityAuditRecord,
    HiredProfileSubmission,
    InterviewInvitation,
    JobApplication,
    JobDescription,
    MatchResult,
    PotentialSimulationEvent,
    Resume,
    ResumeSuggestion,
    ResumeVariant,
    UsageEvent,
    UsageReservation,
    User,
)


def _ids(values: Iterable[object]) -> list[str]:
    return [str(value) for value in values if value is not None]


async def _delete_audits(
    db: AsyncSession,
    *,
    application_ids: list[str] | None = None,
    resume_ids: list[str] | None = None,
    job_ids: list[str] | None = None,
    employer_ids: list[str] | None = None,
) -> None:
    predicates = []
    if application_ids:
        predicates.append(CredibilityAuditRecord.application_id.in_(application_ids))
    if resume_ids:
        predicates.append(CredibilityAuditRecord.resume_id.in_(resume_ids))
    if job_ids:
        predicates.append(CredibilityAuditRecord.job_id.in_(job_ids))
    if employer_ids:
        predicates.append(CredibilityAuditRecord.employer_id.in_(employer_ids))
    if not predicates:
        return
    audit_ids = _ids(
        (await db.execute(select(CredibilityAuditRecord.id).where(or_(*predicates)))).scalars()
    )
    feedback_predicates = []
    if audit_ids:
        feedback_predicates.append(AuditFindingFeedback.audit_record_id.in_(audit_ids))
    if application_ids:
        feedback_predicates.append(AuditFindingFeedback.application_id.in_(application_ids))
    if employer_ids:
        feedback_predicates.append(AuditFindingFeedback.employer_id.in_(employer_ids))
    if feedback_predicates:
        await db.execute(delete(AuditFindingFeedback).where(or_(*feedback_predicates)))
    await db.execute(delete(CredibilityAuditRecord).where(or_(*predicates)))


async def delete_application_graph(db: AsyncSession, application_ids: Iterable[object]) -> None:
    app_ids = _ids(application_ids)
    if not app_ids:
        return
    await _delete_audits(db, application_ids=app_ids)
    await db.execute(
        delete(InterviewInvitation).where(InterviewInvitation.application_id.in_(app_ids))
    )
    await db.execute(
        delete(ApplicationMessage).where(ApplicationMessage.application_id.in_(app_ids))
    )
    await db.execute(delete(JobApplication).where(JobApplication.id.in_(app_ids)))


async def delete_resume_graph(db: AsyncSession, resume_ids: Iterable[object]) -> None:
    ids = _ids(resume_ids)
    if not ids:
        return
    app_ids = _ids(
        (
            await db.execute(select(JobApplication.id).where(JobApplication.resume_id.in_(ids)))
        ).scalars()
    )
    await delete_application_graph(db, app_ids)
    await _delete_audits(db, resume_ids=ids)
    await db.execute(
        delete(PotentialSimulationEvent).where(PotentialSimulationEvent.resume_id.in_(ids))
    )
    await db.execute(delete(InterviewInvitation).where(InterviewInvitation.resume_id.in_(ids)))
    await db.execute(delete(ResumeSuggestion).where(ResumeSuggestion.resume_id.in_(ids)))
    await db.execute(delete(ResumeVariant).where(ResumeVariant.resume_id.in_(ids)))
    await db.execute(delete(MatchResult).where(MatchResult.resume_id.in_(ids)))
    await db.execute(delete(Resume).where(Resume.id.in_(ids)))


async def delete_job_graph(db: AsyncSession, job_ids: Iterable[object]) -> None:
    ids = _ids(job_ids)
    if not ids:
        return
    app_ids = _ids(
        (
            await db.execute(select(JobApplication.id).where(JobApplication.job_id.in_(ids)))
        ).scalars()
    )
    await delete_application_graph(db, app_ids)
    await _delete_audits(db, job_ids=ids)
    await db.execute(
        delete(PotentialSimulationEvent).where(PotentialSimulationEvent.job_id.in_(ids))
    )
    await db.execute(delete(InterviewInvitation).where(InterviewInvitation.job_id.in_(ids)))
    await db.execute(delete(ResumeSuggestion).where(ResumeSuggestion.job_id.in_(ids)))
    await db.execute(delete(ResumeVariant).where(ResumeVariant.job_id.in_(ids)))
    await db.execute(delete(MatchResult).where(MatchResult.job_id.in_(ids)))
    await db.execute(delete(JobDescription).where(JobDescription.id.in_(ids)))


async def delete_user_graph(db: AsyncSession, user_id: str) -> None:
    user_ids = [str(user_id)]
    job_ids = _ids(
        (
            await db.execute(
                select(JobDescription.id).where(JobDescription.employer_id == str(user_id))
            )
        ).scalars()
    )
    resume_ids = _ids(
        (await db.execute(select(Resume.id).where(Resume.user_id == str(user_id)))).scalars()
    )
    await delete_job_graph(db, job_ids)
    await delete_resume_graph(db, resume_ids)

    remaining_apps = _ids(
        (
            await db.execute(
                select(JobApplication.id).where(
                    or_(
                        JobApplication.candidate_id == str(user_id),
                        JobApplication.employer_id == str(user_id),
                    )
                )
            )
        ).scalars()
    )
    await delete_application_graph(db, remaining_apps)
    await _delete_audits(db, employer_ids=user_ids)
    await db.execute(
        delete(InterviewInvitation).where(
            or_(
                InterviewInvitation.candidate_id == str(user_id),
                InterviewInvitation.employer_id == str(user_id),
            )
        )
    )
    await db.execute(delete(ApplicationMessage).where(ApplicationMessage.sender_id == str(user_id)))
    await db.execute(
        delete(HiredProfileSubmission).where(HiredProfileSubmission.user_id == str(user_id))
    )
    await db.execute(delete(UsageEvent).where(UsageEvent.user_id == str(user_id)))
    await db.execute(delete(UsageReservation).where(UsageReservation.user_id == str(user_id)))
    await db.execute(delete(User).where(User.id == str(user_id)))
