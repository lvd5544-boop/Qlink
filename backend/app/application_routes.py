from fastapi import APIRouter, Depends, HTTPException, Query, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime, timezone
from copy import deepcopy
import logging
import uuid

from .auth import get_current_user
from .database import get_db
from .matching_hybrid import full_match_evaluation
from .resume_credibility import build_credibility_report
from .application_status import (
    APPLICATION_STATUSES,
    EMPLOYER_STATUS_LABELS,
    STATUS_LABELS,
    build_clarification_message,
    build_clarification_response_message,
    classify_message_body,
    clarification_request_meta,
    clarification_response_meta,
    extract_claim_text_from_body,
)
from .models_db import (
    ApplicationMessage,
    AuditFindingFeedback,
    CredibilityAuditRecord,
    InterviewInvitation,
    JobApplication,
    JobDescription,
    Resume,
    User,
)
from .claim_threads import (
    answer_claim_thread,
    claim_threads_summary,
    close_open_claims_by_employer,
    mark_application_reviewed,
    open_claim_thread,
    parse_claim_entry_hint,
    recompute_clarification_status,
)
from .application_state import (
    ResumeImmutableError,
    StatusTransitionError,
    capture_resume_snapshot,
    change_application_resume,
    ensure_resume_unchanged,
    get_resume_snapshot,
    allowed_application_actions,
    patch_status_by_role,
    set_application_status,
)
from .application_events import event_bus, sse_event_stream
from .application_authz import (
    ensure_application_has_candidate_authorization,
    ensure_employer_can_access_resume_for_job,
    ensure_employer_can_submit_audit_feedback,
)
from .usage_metering import finalize_quota
from .provider_costs import record_metering_cost_if_called
from .billing_accounts import reserve_feature_entitlement
from .email_service import send_email
from .claim_passport import (
    add_evidence as passport_add_evidence,
    application_claim_snapshot_summary,
    claim_for_source_key,
    mark_application_claim_reviewed,
    note_clarification_requested,
    record_application_conflict,
    snapshot_application_claims,
    sync_resume_claims,
)

router = APIRouter(prefix="/applications", tags=["岗位申请"])


class ApplyRequest(BaseModel):
    job_id: str
    resume_id: str
    cover_letter: Optional[str] = None


class ConflictReviewRequest(BaseModel):
    claim_id: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=2000)


class MessageRequest(BaseModel):
    body: str


class StatusUpdateRequest(BaseModel):
    status: str


class ClarificationRequest(BaseModel):
    claim_id: Optional[str] = None
    claim_text: str = Field(..., min_length=1)
    questions: List[str] = Field(default_factory=list)
    evidence_suggestions: List[str] = Field(default_factory=list)


class ClarificationResponseRequest(BaseModel):
    body: str = Field(..., min_length=1)
    claim_id: Optional[str] = None


class ReviewRequest(BaseModel):
    claim_id: Optional[str] = None


class AuditFeedbackRequest(BaseModel):
    label: str = Field(..., description="useful | false_positive | unclear")
    claim_id: Optional[str] = None
    finding_id: Optional[str] = None
    finding_snapshot: Optional[dict] = None
    note: Optional[str] = None
    audit_record_id: Optional[str] = None
    application_id: Optional[str] = None


def _normalize_message(msg: ApplicationMessage) -> tuple[str, dict]:
    kind = classify_message_body(msg.body, getattr(msg, "message_kind", None))
    meta = getattr(msg, "message_meta", None) or {}
    return kind, meta


def _message_payload(msg: ApplicationMessage, current_user: User) -> dict:
    kind, meta = _normalize_message(msg)
    return {
        "id": str(msg.id),
        "application_id": msg.application_id,
        "sender_id": msg.sender_id,
        "body": msg.body,
        "message_kind": kind,
        "message_meta": meta,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "is_mine": msg.sender_id == str(current_user.id),
    }


def _clarification_message_summary(msg: ApplicationMessage) -> dict:
    kind, meta = _normalize_message(msg)
    claim_text = meta.get("claim_text") or extract_claim_text_from_body(msg.body)
    return {
        "message_id": str(msg.id),
        "body": msg.body,
        "message_kind": kind,
        "claim_id": meta.get("claim_id"),
        "claim_text": claim_text,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


async def _load_clarification_messages(
    db: AsyncSession,
    application_id: str,
    limit: int = 3,
) -> dict:
    stmt = (
        select(ApplicationMessage)
        .where(ApplicationMessage.application_id == application_id)
        .order_by(ApplicationMessage.created_at.desc())
    )
    result = await db.execute(stmt)
    messages = list(result.scalars().all())

    requests = []
    responses = []
    latest = None
    for msg in messages:
        summary = _clarification_message_summary(msg)
        kind = summary["message_kind"]
        if kind == "clarification_request" and len(requests) < limit:
            requests.append(summary)
        elif kind == "clarification_response" and len(responses) < limit:
            responses.append(summary)
        if latest is None and kind in {"clarification_request", "clarification_response"}:
            latest = summary

    return {
        "clarification_requests": requests,
        "clarification_responses": responses,
        "latest_clarification_message": latest,
    }


async def _save_clarification_answer_to_resume(
    resume: Resume,
    *,
    claim_id: Optional[str],
    claim_text: Optional[str],
    answer: str,
    application_id: str,
    job_title: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "claim_id": claim_id,
        "claim_text": claim_text,
        "answer": answer.strip(),
        "application_id": application_id,
        "job_title": job_title,
        "source": "employer_clarification",
        "saved_at": now,
        **parse_claim_entry_hint(claim_id),
    }
    current = dict(resume.parsed_json or {})
    existing = list(current.get("clarification_answers") or [])
    existing.append(entry)
    current["clarification_answers"] = existing[-20:]
    resume.parsed_json = current


async def _mark_viewed_if_submitted(
    app: JobApplication, db: AsyncSession, *, actor_id: Optional[str] = None
) -> None:
    if app.status == "submitted":
        set_application_status(
            app,
            "viewed",
            action="employer_view",
            actor_role="employer",
            actor_id=actor_id,
            source="auto_viewed",
        )
        await db.commit()
        await db.refresh(app)


async def _get_or_create_application_for_clarification(
    db: AsyncSession,
    job: JobDescription,
    resume: Resume,
) -> JobApplication:
    """仅复用候选人已授权的真实申请；不得由任意 resume 制造授权关系。"""
    stmt = (
        select(JobApplication)
        .where(
            JobApplication.job_id == job.id,
            JobApplication.candidate_id == resume.user_id,
            JobApplication.employer_id == job.employer_id,
        )
        .order_by(JobApplication.created_at.desc())
        .with_for_update()
    )
    result = await db.execute(stmt)
    application = result.scalars().first()
    if application:
        ensure_resume_unchanged(application, str(resume.id))
        ensure_application_has_candidate_authorization(application)
        return application
    raise HTTPException(status_code=404, detail="资源不存在或无权访问")


async def _send_clarification_for_application(
    db: AsyncSession,
    application: JobApplication,
    employer: User,
    req: ClarificationRequest,
    *,
    commit: bool = True,
    notify: bool = True,
) -> dict:
    job = await db.get(JobDescription, application.job_id)
    if (
        not job
        or job.employer_id != str(employer.id)
        or application.employer_id != str(employer.id)
    ):
        raise HTTPException(status_code=403, detail="无权操作该申请")
    ensure_application_has_candidate_authorization(application)
    if application.status in {"accepted", "rejected", "interview_invited"}:
        raise HTTPException(status_code=409, detail="当前申请状态不能发起澄清")

    resume = await db.get(Resume, application.resume_id)
    if resume:
        await sync_resume_claims(
            db,
            resume,
            actor_id=str(employer.id),
            reason="clarification_requested",
        )
        passport_claim = await claim_for_source_key(db, str(resume.id), req.claim_id)
        if passport_claim:
            await note_clarification_requested(
                db,
                passport_claim,
                application_id=str(application.id),
                employer_id=str(employer.id),
            )

    questions = [q.strip() for q in req.questions if q and q.strip()]
    if not questions:
        raise HTTPException(status_code=400, detail="请至少提供一个需澄清的问题")

    body = build_clarification_message(
        req.claim_text.strip(),
        questions,
        req.evidence_suggestions,
    )
    meta = clarification_request_meta(
        req.claim_text.strip(),
        questions,
        req.claim_id,
        req.evidence_suggestions,
    )
    msg = ApplicationMessage(
        application_id=str(application.id),
        sender_id=str(employer.id),
        body=body,
        message_kind="clarification_request",
        message_meta=meta,
    )
    db.add(msg)
    await db.flush()
    open_claim_thread(
        application,
        claim_id=req.claim_id,
        claim_text=req.claim_text.strip(),
        request_message_id=str(msg.id),
        questions=questions,
    )
    set_application_status(
        application,
        recompute_clarification_status(application),
        action="create_claim_request",
        actor_role="employer",
        actor_id=str(employer.id),
        source="clarification_request",
    )
    if commit:
        await db.commit()
        await db.refresh(msg)
        await db.refresh(application)
        if notify:
            await _notify_clarification_requested(
                db,
                application=application,
                employer=employer,
                message_id=str(msg.id),
                claim_id=req.claim_id,
            )

    return {
        "status": "ok",
        "message": _message_payload(msg, employer),
        "application": _application_payload(application, job),
        "claim_id": req.claim_id,
        "application_id": str(application.id),
        **claim_threads_summary(application),
    }


async def _notify_clarification_requested(
    db: AsyncSession,
    *,
    application: JobApplication,
    employer: User,
    message_id: str,
    claim_id: str | None,
) -> None:
    """Best-effort notifications after the business transaction commits."""
    job = await db.get(JobDescription, application.job_id)
    try:
        await event_bus.publish(
            application_id=str(application.id),
            event_type="clarification_request",
            payload={
                "claim_id": claim_id,
                "message_id": str(message_id),
                "status": application.status,
            },
            candidate_id=application.candidate_id,
            employer_id=str(employer.id),
        )
    except Exception:
        pass
    try:
        candidate = await db.get(User, application.candidate_id)
        if candidate and candidate.email:
            await send_email(
                candidate.email,
                f"岗位「{job.title if job else ''}」需要您补充说明",
                "<p>招聘方就履历主张发起了澄清请求，请登录「已申请岗位」回复。</p>",
            )
    except Exception:
        pass


class _SnapshotResume:
    """
    只读简历代理：以投递时快照的 parsed_json 覆盖当前简历，
    其余属性委托真实 Resume，供历史审计使用。
    """

    def __init__(self, real_resume: Resume, parsed_json: dict):
        self._real = real_resume
        self.parsed_json = parsed_json

    def __getattr__(self, item):
        return getattr(self._real, item)


def _application_payload(app: JobApplication, job: JobDescription | None = None):
    threads = claim_threads_summary(app)
    return {
        "id": str(app.id),
        "job_id": app.job_id,
        "job_title": job.title if job else "",
        "employer_id": app.employer_id,
        "candidate_id": app.candidate_id,
        "resume_id": app.resume_id,
        "status": app.status,
        "status_label": STATUS_LABELS.get(app.status, app.status),
        "employer_status_label": EMPLOYER_STATUS_LABELS.get(app.status, app.status),
        "cover_letter": app.cover_letter,
        "created_at": app.created_at.isoformat() if app.created_at else None,
        "updated_at": app.updated_at.isoformat() if app.updated_at else None,
        "employer_reviewed_at": threads.get("employer_reviewed_at"),
        "open_claim_count": threads.get("open_claim_count", 0),
        "answered_unreviewed_count": threads.get("answered_unreviewed_count", 0),
        "claim_threads": threads.get("claim_threads", []),
        "allowed_actions": {
            role: allowed_application_actions(
                app,
                actor_role=role,
                open_claim_count=threads.get("open_claim_count", 0),
                answered_unreviewed_count=threads.get(
                    "answered_unreviewed_count",
                    0,
                ),
            )
            for role in ("candidate", "employer")
        },
        "current_resume_version_id": (app.pipeline_meta or {}).get("current_resume_version_id")
        if isinstance(app.pipeline_meta, dict)
        else None,
        "initial_submission_snapshot": deepcopy(
            (app.pipeline_meta or {}).get("initial_submission_snapshot")
        )
        if isinstance(app.pipeline_meta, dict)
        else None,
    }


def _redact_report_for_storage(report: dict) -> dict:
    if not isinstance(report, dict):
        return {}
    # PR15: never persist risk_score on new audits (omit entirely; do not write 0).
    return {
        "overall_status": report.get("overall_status"),
        "status_label": report.get("status_label"),
        "findings": report.get("findings") or [],
        "claim_reasoning": {
            "items": (report.get("claim_reasoning") or {}).get("items") or [],
            "overall_status": (report.get("claim_reasoning") or {}).get("overall_status"),
        },
        "disclaimer": report.get("disclaimer"),
    }


def _omit_risk_score(payload: dict) -> dict:
    """PR15: new credibility API responses must omit risk_score entirely."""
    if not isinstance(payload, dict):
        return payload
    cleaned = dict(payload)
    cleaned.pop("risk_score", None)
    report = cleaned.get("report")
    if isinstance(report, dict):
        report = dict(report)
        report.pop("risk_score", None)
        claim = report.get("claim_reasoning")
        if isinstance(claim, dict):
            claim = dict(claim)
            claim.pop("risk_score", None)
            report["claim_reasoning"] = claim
        cleaned["report"] = report
    return cleaned


async def _persist_credibility_audit(
    db: AsyncSession,
    *,
    employer_id: str,
    job: JobDescription,
    resume: Resume,
    application: Optional[JobApplication],
    report: dict,
    resume_snapshot: Optional[dict] = None,
) -> CredibilityAuditRecord:
    stored_report = _redact_report_for_storage(report)
    if resume_snapshot:
        stored_report["application_resume_snapshot"] = deepcopy(resume_snapshot)
    record = CredibilityAuditRecord(
        employer_id=employer_id,
        job_id=str(job.id),
        resume_id=str(resume.id),
        application_id=str(application.id) if application else None,
        overall_status=report.get("overall_status"),
        # PR15 hard constraint: new rows may only store NULL (never 0 or any score).
        risk_score=None,
        report=stored_report,
    )
    db.add(record)
    await db.flush()
    return record


async def _credibility_audit_response(
    db: AsyncSession,
    *,
    employer: User,
    job: JobDescription,
    resume: Resume,
    application: Optional[JobApplication] = None,
    resume_snapshot: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    reservation = await reserve_feature_entitlement(
        db,
        actor=employer,
        feature="credibility_audit",
        idempotency_key=idempotency_key or str(uuid.uuid4()),
        request_payload={
            "job_id": str(job.id),
            "resume_id": str(resume.id),
            "application_id": str(application.id) if application else None,
            "resume_snapshot": resume_snapshot,
        },
        reservation_meta={"entrypoint": "credibility_audit"},
    )
    if not reservation["created"]:
        raise HTTPException(
            status_code=409,
            detail={"error": "idempotency_replayed", **reservation},
        )
    metering: dict = {}
    try:
        report = build_credibility_report(
            resume.parsed_json,
            job.parsed_json if job else None,
        )
        if application:
            report["claim_passport"] = {
                "scope": "application_submission_snapshot",
                "provenance_only": True,
                "claims": await application_claim_snapshot_summary(db, str(application.id)),
            }
        metering = report.pop("_metering", {})
        record = await _persist_credibility_audit(
            db,
            employer_id=str(employer.id),
            job=job,
            resume=resume,
            application=application,
            report=report,
            resume_snapshot=resume_snapshot,
        )
    except Exception:
        await db.rollback()
        await record_metering_cost_if_called(
            db,
            metering=metering,
            reservation_id=reservation["reservation_id"],
            user_id=str(employer.id),
            organization_id=(
                reservation.get("billing_account_id")
                if reservation.get("billing_account_type") == "organization"
                else None
            ),
            feature="credibility_audit",
            prompt_version="credibility-audit-v1",
        )
        await finalize_quota(
            db,
            reservation["reservation_id"],
            succeeded=False,
            failure_reason="audit_error",
            meta={"model_called": bool(metering.get("model_called"))},
        )
        raise

    await record_metering_cost_if_called(
        db,
        metering=metering,
        reservation_id=reservation["reservation_id"],
        user_id=str(employer.id),
        organization_id=(
            reservation.get("billing_account_id")
            if reservation.get("billing_account_type") == "organization"
            else None
        ),
        feature="credibility_audit",
        prompt_version="credibility-audit-v1",
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
            "audit_record_id": str(record.id),
            "job_id": str(job.id),
        },
    )
    # METERING_ENABLED=false 时 finalize 是 no-op；审计业务记录仍必须提交。
    await db.commit()
    return _omit_risk_score(
        {
            "job_id": str(job.id),
            "resume_id": str(resume.id),
            "application_id": str(application.id) if application else None,
            "has_application": application is not None,
            "application_status": application.status if application else None,
            "job_title": job.title if job else "",
            "candidate_name": (resume.parsed_json or {}).get("name") or "匿名",
            "audit_record_id": str(record.id),
            "application_resume_version_id": (resume_snapshot or {}).get("version_id"),
            "snapshot_captured_at": (resume_snapshot or {}).get("captured_at"),
            "snapshot_source": (resume_snapshot or {}).get("source"),
            "snapshot_status": (resume_snapshot or {}).get("snapshot_status"),
            "report": report,
            "claim_threads": claim_threads_summary(application) if application else None,
        }
    )


async def _ensure_participant(app: JobApplication, user: User):
    user_id = str(user.id)
    if user_id not in {app.candidate_id, app.employer_id}:
        raise HTTPException(status_code=403, detail="无权查看该申请")


async def _load_application_for_update(
    db: AsyncSession, application_id: str
) -> Optional[JobApplication]:
    result = await db.execute(
        select(JobApplication).where(JobApplication.id == application_id).with_for_update()
    )
    return result.scalars().first()


async def _lock_application_identity(db: AsyncSession, *, job_id: str, candidate_id: str) -> None:
    """Serialize PostgreSQL application creation for one job/candidate pair."""
    if db.get_bind().dialect.name != "postgresql":
        return
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
        {"identity": f"job_application:{job_id}:{candidate_id}"},
    )


@router.post("")
async def apply_job(
    req: ApplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "candidate":
        raise HTTPException(status_code=403, detail="仅求职者可申请岗位")

    job = await db.get(JobDescription, req.job_id)
    if not job or (job.parsed_json or {}).get("_publication_status") == "draft":
        raise HTTPException(status_code=404, detail="岗位不存在")

    resume = await db.get(Resume, req.resume_id)
    if not resume or resume.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="简历不存在或不属于当前用户")

    await _lock_application_identity(
        db,
        job_id=req.job_id,
        candidate_id=str(current_user.id),
    )
    existing = await db.execute(
        select(JobApplication).where(
            JobApplication.job_id == req.job_id,
            JobApplication.candidate_id == str(current_user.id),
        )
    )
    existing_app = existing.scalars().first()
    if existing_app:
        # 已投递申请 resume_id 不可静默变更；更换须走显式换简历接口
        return {
            "status": "exists",
            "resume_changed": False,
            "resume_change_required_explicit": existing_app.resume_id != req.resume_id,
            "application": _application_payload(existing_app, job),
        }

    application = JobApplication(
        job_id=req.job_id,
        employer_id=job.employer_id,
        candidate_id=str(current_user.id),
        resume_id=req.resume_id,
        cover_letter=req.cover_letter,
    )
    capture_resume_snapshot(
        application,
        resume,
        actor_id=str(current_user.id),
        source="candidate_applied",
    )
    db.add(application)
    await db.flush()
    await snapshot_application_claims(
        db,
        application,
        resume,
        actor_id=str(current_user.id),
    )

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


class ChangeResumeRequest(BaseModel):
    resume_id: str
    confirm: bool = False
    reason: Optional[str] = None


@router.patch("/{application_id}/resume")
async def change_application_resume_endpoint(
    application_id: str,
    req: ChangeResumeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """候选人显式更换申请简历：需确认，保留原快照与更换记录，不静默覆盖历史。"""
    if current_user.role != "candidate":
        raise HTTPException(status_code=403, detail="仅求职者可更换本人申请的简历")

    app = await _load_application_for_update(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="申请不存在")
    if app.candidate_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权修改该申请")
    if app.status in {"accepted", "rejected"}:
        raise HTTPException(status_code=409, detail="终态申请不能更换简历")

    if not req.confirm:
        raise HTTPException(status_code=400, detail="更换简历需显式确认（confirm=true）")

    resume = await db.get(Resume, req.resume_id)
    if not resume or resume.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="简历不存在或不属于当前用户")

    if str(app.resume_id) == str(resume.id):
        raise HTTPException(status_code=400, detail="新简历必须与当前简历不同")

    meta = app.pipeline_meta if isinstance(app.pipeline_meta, dict) else {}
    audit_count = (
        await db.execute(
            select(func.count())
            .select_from(CredibilityAuditRecord)
            .where(CredibilityAuditRecord.application_id == application_id)
        )
    ).scalar_one()
    employer_message_count = (
        await db.execute(
            select(func.count())
            .select_from(ApplicationMessage)
            .where(
                ApplicationMessage.application_id == application_id,
                ApplicationMessage.sender_id == app.employer_id,
            )
        )
    ).scalar_one()
    invitation_count = (
        await db.execute(
            select(func.count())
            .select_from(InterviewInvitation)
            .where(InterviewInvitation.application_id == application_id)
        )
    ).scalar_one()
    if (
        app.status != "submitted"
        or audit_count
        or employer_message_count
        or invitation_count
        or meta.get("last_employer_activity_at")
    ):
        raise HTTPException(
            status_code=409,
            detail="招聘方已查看或处理该申请，不能覆盖其已看到的简历版本",
        )

    record = change_application_resume(
        app,
        new_resume=resume,
        actor_id=str(current_user.id),
        reason=req.reason,
    )
    await db.commit()
    await db.refresh(app)
    job = await db.get(JobDescription, app.job_id)
    return {
        "status": "ok",
        "resume_change": record,
        "application": _application_payload(app, job),
    }


@router.get("/mine")
async def my_applications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(JobApplication)
        .where(JobApplication.candidate_id == str(current_user.id))
        .order_by(JobApplication.created_at.desc())
    )
    result = await db.execute(stmt)
    applications = result.scalars().all()

    payload = []
    for app in applications:
        job = await db.get(JobDescription, app.job_id)
        payload.append(_application_payload(app, job))
    return payload


@router.get("/mine/clarification-summary")
async def my_clarification_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """求职者：待澄清任务数量（用于导航角标）。"""
    if current_user.role != "candidate":
        raise HTTPException(status_code=403, detail="仅求职者可查看")

    stmt = (
        select(func.count())
        .select_from(JobApplication)
        .where(
            JobApplication.candidate_id == str(current_user.id),
            JobApplication.status == "needs_clarification",
        )
    )
    result = await db.execute(stmt)
    pending_count = result.scalar() or 0
    return {"pending_clarification_count": pending_count}


@router.get("/employer/inbox-summary")
async def employer_inbox_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """招聘方：待复核澄清回复 / 面试邀请相关角标。"""
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可查看")

    stmt = select(JobApplication).where(JobApplication.employer_id == str(current_user.id))
    result = await db.execute(stmt)
    apps = result.scalars().all()
    pending_review = 0
    clarified_count = 0
    for app in apps:
        summary = claim_threads_summary(app)
        pending_review += summary.get("answered_unreviewed_count") or 0
        if app.status == "clarified":
            clarified_count += 1
    return {
        "pending_review_count": pending_review,
        "clarified_count": clarified_count,
        "open_applications": len(apps),
    }


@router.get("/employer/all")
async def employer_all_applications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """招聘方：跨岗位查看全部申请，作为统一申请审阅入口。"""
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可查看")

    stmt = (
        select(JobApplication)
        .where(JobApplication.employer_id == str(current_user.id))
        .order_by(JobApplication.created_at.desc())
    )
    result = await db.execute(stmt)
    payload = []
    for app in result.scalars().all():
        job = await db.get(JobDescription, app.job_id)
        snapshot = get_resume_snapshot(app) or {}
        parsed = snapshot.get("parsed_json") or {}
        payload.append(
            {
                **_application_payload(app, job),
                "candidate_name": parsed.get("name") or "匿名候选人",
                "expected_title": parsed.get("expected_job_title") or "未填写",
            }
        )
    return payload


async def _snapshot_material(
    db: AsyncSession,
    snapshot: dict,
    *,
    version_id: Optional[str] = None,
) -> dict:
    data = deepcopy(snapshot or {})
    resume_id = data.get("resume_id")
    raw_text = data.get("raw_text") or ""
    if not raw_text and resume_id:
        resume = await db.get(Resume, resume_id)
        raw_text = resume.raw_text if resume else ""
    return {
        "version_id": version_id or data.get("version_id"),
        "resume_id": resume_id,
        "parsed_json": deepcopy(
            data.get("parsed_json")
            or data.get("snapshot_json")
            or {}
        ),
        "raw_text": raw_text or "",
        "captured_at": data.get("captured_at") or data.get("created_at"),
        "source": data.get("source"),
        "content_hash": data.get("content_hash"),
        "snapshot_status": data.get("snapshot_status", "reliable"),
    }


@router.get("/{application_id}/materials")
async def application_materials(
    application_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """申请参与方查看已授权的投递原文和不可变简历版本。"""
    application = await db.get(JobApplication, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="申请不存在")
    await _ensure_participant(application, current_user)

    meta = application.pipeline_meta if isinstance(application.pipeline_meta, dict) else {}
    initial = meta.get("initial_submission_snapshot") or meta.get("resume_snapshot") or {}
    versions = []
    for version in meta.get("resume_versions") or []:
        if isinstance(version, dict):
            versions.append(
                await _snapshot_material(
                    db,
                    version,
                    version_id=version.get("version_id"),
                )
            )
    current = get_resume_snapshot(application) or initial
    if not versions and initial:
        versions.append(await _snapshot_material(db, initial, version_id="v1"))

    return {
        "application_id": str(application.id),
        "initial_submission": await _snapshot_material(db, initial, version_id="v1"),
        "current_submission": await _snapshot_material(db, current),
        "current_resume_version_id": meta.get("current_resume_version_id") or "v1",
        "versions": versions,
        "disclaimer": "仅展示候选人对本次申请明确授权的投递快照；后续私密修改不会自动同步。",
    }


@router.get("/mine/evaluations")
async def my_applications_with_evaluations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """已申请岗位 + v2 十维评分与职业建议。"""
    if current_user.role != "candidate":
        raise HTTPException(status_code=403, detail="仅求职者可查看")

    stmt = (
        select(JobApplication)
        .where(JobApplication.candidate_id == str(current_user.id))
        .order_by(JobApplication.created_at.desc())
    )
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

        pending_clarification = None
        clarification_ctx = await _load_clarification_messages(db, str(app.id))
        if app.status == "needs_clarification":
            pending_clarification = next(
                (
                    r
                    for r in clarification_ctx["clarification_requests"]
                    if classify_message_body(r.get("body", ""), r.get("message_kind"))
                    == "clarification_request"
                ),
                clarification_ctx["latest_clarification_message"],
            )

        payload.append(
            {
                **base,
                "job_location": (job.parsed_json or {}).get("location") if job else None,
                "job_salary": (job.parsed_json or {}).get("salary_range") if job else None,
                "evaluation": evaluation,
                "pending_clarification": pending_clarification,
                **clarification_ctx,
            }
        )
    return payload


@router.get("/job/{job_id}")
async def job_applications(
    job_id: str,
    status: Optional[str] = Query(None, description="按申请状态筛选"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可查看岗位申请")

    job = await db.get(JobDescription, job_id)
    if not job or job.employer_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="岗位不存在或无权查看")

    stmt = (
        select(JobApplication)
        .where(JobApplication.job_id == job_id)
        .order_by(JobApplication.created_at.desc())
    )
    if status:
        if status not in APPLICATION_STATUSES:
            raise HTTPException(status_code=400, detail="无效的申请状态")
        stmt = stmt.where(JobApplication.status == status)
    result = await db.execute(stmt)
    applications = result.scalars().all()

    payload = []
    for app in applications:
        resume = await db.get(Resume, app.resume_id)
        parsed = resume.parsed_json if resume else {}
        payload.append(
            {
                **_application_payload(app, job),
                "candidate_name": parsed.get("name") or "匿名候选人",
                "expected_title": parsed.get("expected_job_title") or "未填写",
                "resume_uploaded_at": resume.uploaded_at.isoformat()
                if resume and resume.uploaded_at
                else None,
            }
        )
    return payload


@router.get("/job/{job_id}/resume/{resume_id}/credibility-audit")
async def job_resume_credibility_audit(
    job_id: str,
    resume_id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    招聘方：对已关联申请的候选人做履历一致性审计。

    MVP 授权：当前雇主拥有岗位，且存在 job_id+resume_id 精确申请；
    仅有全局 MatchResult 不构成授权。无权限统一 404。
    """
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可查看可信度审计报告")

    job, resume, application = await ensure_employer_can_access_resume_for_job(
        db,
        employer_id=str(current_user.id),
        job_id=job_id,
        resume_id=resume_id,
    )

    snapshot = get_resume_snapshot(application)
    if not snapshot or not snapshot.get("parsed_json"):
        raise HTTPException(status_code=409, detail="该申请没有可用的简历版本快照")
    resume = _SnapshotResume(resume, snapshot["parsed_json"])
    return await _credibility_audit_response(
        db,
        employer=current_user,
        job=job,
        resume=resume,
        application=application,
        resume_snapshot=snapshot,
        idempotency_key=idempotency_key,
    )


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

    if current_user.role == "employer" and app.status == "submitted":
        await _mark_viewed_if_submitted(app, db, actor_id=str(current_user.id))

    stmt = (
        select(ApplicationMessage)
        .where(ApplicationMessage.application_id == application_id)
        .order_by(ApplicationMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()

    return [_message_payload(msg, current_user) for msg in messages]


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
    if app.status in {"accepted", "rejected"}:
        raise HTTPException(status_code=409, detail="终态申请不能新增消息")

    msg = ApplicationMessage(
        application_id=application_id,
        sender_id=str(current_user.id),
        body=body,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    await event_bus.publish(
        application_id=application_id,
        event_type="message",
        payload={"message_id": str(msg.id)},
        candidate_id=app.candidate_id,
        employer_id=app.employer_id,
    )
    return _message_payload(msg, current_user)


@router.patch("/{application_id}/status")
async def update_application_status(
    application_id: str,
    req: StatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    new_status = req.status.strip()

    app = await _load_application_for_update(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="申请不存在")

    # 归属校验（授权），业务状态限制交由领域服务
    if current_user.role == "employer":
        job = await db.get(JobDescription, app.job_id)
        if not job or job.employer_id != str(current_user.id):
            raise HTTPException(status_code=403, detail="无权修改该申请")
    elif current_user.role == "candidate":
        if app.candidate_id != str(current_user.id):
            raise HTTPException(status_code=403, detail="无权修改该申请")
    else:
        raise HTTPException(status_code=403, detail="无权修改申请状态")

    try:
        patch_status_by_role(app, new_status, current_user.role, actor_id=str(current_user.id))
    except StatusTransitionError as e:
        raise HTTPException(status_code=e.code, detail=str(e))

    await db.commit()
    await db.refresh(app)
    job = await db.get(JobDescription, app.job_id)
    return {"status": "ok", "application": _application_payload(app, job)}


class CloseClarificationRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


@router.post("/{application_id}/clarification/close")
async def close_clarification(
    application_id: str,
    req: CloseClarificationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """招聘方显式「人工关闭澄清」：关闭所有开放 Claim 并留痕，不伪装成候选人回复。"""
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可关闭澄清")

    app = await _load_application_for_update(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="申请不存在")
    job = await db.get(JobDescription, app.job_id)
    if not job or job.employer_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权操作该申请")

    if app.status in {"accepted", "rejected", "interview_invited"}:
        raise HTTPException(status_code=409, detail="当前申请状态不能关闭澄清")
    reason = req.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="关闭原因不能为空")
    closed = close_open_claims_by_employer(
        app,
        employer_id=str(current_user.id),
        reason=reason,
    )
    if not closed:
        raise HTTPException(status_code=400, detail="当前没有待关闭的开放 Claim")

    new_status = recompute_clarification_status(app)
    set_application_status(
        app,
        new_status,
        action="employer_closes_clarification",
        actor_role="employer",
        actor_id=str(current_user.id),
        reason=reason,
        source="employer_close_clarification",
    )
    await db.commit()
    await db.refresh(app)
    job = await db.get(JobDescription, app.job_id)
    return {
        "status": "ok",
        "closed_claim_count": len(closed),
        "application": _application_payload(app, job),
        **claim_threads_summary(app),
    }


@router.post("/job/{job_id}/resume/{resume_id}/clarification-requests")
async def send_clarification_for_resume(
    job_id: str,
    resume_id: str,
    req: ClarificationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """招聘方仅可对候选人真实投递且版本一致的申请发起澄清。"""
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可发起澄清请求")

    job = await db.get(JobDescription, job_id)
    if not job or job.employer_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="资源不存在或无权访问")

    resume = await db.get(Resume, resume_id)
    if not resume or not resume.parsed_json:
        raise HTTPException(status_code=404, detail="资源不存在或无权访问")

    try:
        application = await _get_or_create_application_for_clarification(db, job, resume)
    except ResumeImmutableError as e:
        raise HTTPException(status_code=e.code, detail=str(e))
    return await _send_clarification_for_application(db, application, current_user, req)


@router.post("/{application_id}/clarification-requests")
async def send_clarification_request(
    application_id: str,
    req: ClarificationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """招聘方针对 claim 风险项发起澄清请求，自动发送消息并更新状态。"""
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可发起澄清请求")

    app = await _load_application_for_update(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="申请不存在")

    return await _send_clarification_for_application(db, app, current_user, req)


@router.post("/{application_id}/clarification-response")
async def send_clarification_response(
    application_id: str,
    req: ClarificationResponseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """求职者回复澄清请求；按 claim 关闭线程，全部关闭后才标记 clarified。"""
    if current_user.role != "candidate":
        raise HTTPException(status_code=403, detail="仅求职者可回复澄清请求")

    app = await _load_application_for_update(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="申请不存在")
    if app.candidate_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权回复该申请")
    if app.status in {"accepted", "rejected", "interview_invited"}:
        raise HTTPException(status_code=409, detail="当前申请状态不能回复澄清")
    if app.status != "needs_clarification" and not claim_threads_summary(app).get(
        "open_claim_count"
    ):
        raise HTTPException(status_code=400, detail="当前申请不在待澄清状态")

    ctx = await _load_clarification_messages(db, application_id, limit=10)
    open_requests = ctx["clarification_requests"]
    threads_summary = claim_threads_summary(app)
    open_threads = [
        t for t in (threads_summary.get("claim_threads") or []) if t.get("status") == "open"
    ]
    open_count = max(len(open_threads), int(threads_summary.get("open_claim_count") or 0))

    claim_id = (req.claim_id or "").strip() or None
    if open_count > 1 and not claim_id:
        raise HTTPException(
            status_code=422,
            detail="存在多条待澄清 Claim，请指定 claim_id 后再回复。",
        )

    claim_text = None
    request_message_id = None
    if claim_id:
        latest_request = next((r for r in open_requests if r.get("claim_id") == claim_id), None)
        if latest_request is not None:
            request_message_id = latest_request.get("message_id")
            claim_text = latest_request.get("claim_text") or extract_claim_text_from_body(
                latest_request.get("body", "")
            )
        else:
            thread = next((t for t in open_threads if t.get("claim_id") == claim_id), None)
            if thread is None:
                # 也接受 thread_key == claim_id
                thread = next(
                    (t for t in open_threads if t.get("thread_key") == claim_id),
                    None,
                )
            if thread is None:
                raise HTTPException(status_code=400, detail="claim_id 不属于该申请的开放澄清线程")
            request_message_id = thread.get("request_message_id")
            claim_text = thread.get("claim_text")
            claim_id = thread.get("claim_id") or claim_id
    elif open_count == 1:
        # 兼容：恰好一条开放 Claim 时可自动绑定
        thread = open_threads[0] if open_threads else None
        if thread:
            claim_id = thread.get("claim_id")
            claim_text = thread.get("claim_text")
            request_message_id = thread.get("request_message_id")
        else:
            latest_request = next(iter(open_requests), None)
            if latest_request:
                request_message_id = latest_request.get("message_id")
                claim_text = latest_request.get("claim_text") or extract_claim_text_from_body(
                    latest_request.get("body", "")
                )
                claim_id = latest_request.get("claim_id")
        logging.getLogger(__name__).info(
            "clarification_response single-open auto-bind application_id=%s claim_id=%s",
            application_id,
            claim_id,
        )
    else:
        latest_request = next(iter(open_requests), None)
        if latest_request:
            request_message_id = latest_request.get("message_id")
            claim_text = latest_request.get("claim_text") or extract_claim_text_from_body(
                latest_request.get("body", "")
            )
            claim_id = latest_request.get("claim_id")

    response_text = req.body.strip()
    if not response_text:
        raise HTTPException(status_code=422, detail="澄清回复不能为空")
    body = build_clarification_response_message(response_text)
    meta = clarification_response_meta(claim_id, claim_text, request_message_id)
    msg = ApplicationMessage(
        application_id=application_id,
        sender_id=str(current_user.id),
        body=body,
        message_kind="clarification_response",
        message_meta=meta,
    )
    db.add(msg)
    await db.flush()

    try:
        answer_claim_thread(
            app,
            claim_id=claim_id,
            claim_text=claim_text,
            response_message_id=str(msg.id),
            request_message_id=request_message_id,
            allow_single_open_fallback=(open_count <= 1),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    target_status = recompute_clarification_status(app)
    set_application_status(
        app,
        target_status,
        action=(
            "candidate_answers_some"
            if target_status == "needs_clarification"
            else "candidate_answers_all"
        ),
        actor_role="candidate",
        actor_id=str(current_user.id),
        source="clarification_response",
    )

    resume = await db.get(Resume, app.resume_id)
    if resume:
        job = await db.get(JobDescription, app.job_id)
        await _save_clarification_answer_to_resume(
            resume,
            claim_id=claim_id,
            claim_text=claim_text,
            answer=req.body,
            application_id=application_id,
            job_title=job.title if job else "",
        )
        # Bridge legacy clarification threads to the Passport's formal evidence
        # record. A claim key may be absent on old records; those remain legacy.
        passport_claim = await claim_for_source_key(db, str(resume.id), claim_id)
        if passport_claim:
            await passport_add_evidence(
                db,
                passport_claim,
                actor_id=str(current_user.id),
                evidence_type="user_statement",
                summary=req.body,
                source=f"application:{application_id}:clarification_response",
            )

    await db.commit()
    await db.refresh(msg)
    await db.refresh(app)
    job = await db.get(JobDescription, app.job_id)

    await event_bus.publish(
        application_id=application_id,
        event_type="clarification_response",
        payload={"claim_id": claim_id, "status": app.status, "message_id": str(msg.id)},
        candidate_id=app.candidate_id,
        employer_id=app.employer_id,
    )
    try:
        employer = await db.get(User, app.employer_id) if app.employer_id else None
        if employer and employer.email:
            await send_email(
                employer.email,
                f"候选人已回复澄清 · {job.title if job else ''}",
                "<p>候选人已回复澄清请求，请登录申请详情复核。</p>",
            )
    except Exception:
        pass

    return {
        "status": "ok",
        "message": _message_payload(msg, current_user),
        "application": _application_payload(app, job),
        "claim_id": claim_id,
        **claim_threads_summary(app),
    }


@router.get("/{application_id}/credibility-audit")
async def application_credibility_audit(
    application_id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    招聘方：履历逻辑一致性 & 可信度筛查报告。
    输出需澄清项与追问建议，不判定造假。仅招聘方可访问。
    """
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可查看可信度审计报告")

    app = await db.get(JobApplication, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="申请不存在")

    job = await db.get(JobDescription, app.job_id)
    if not job or job.employer_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权查看该申请")
    ensure_application_has_candidate_authorization(app)

    if app.status == "submitted":
        await _mark_viewed_if_submitted(app, db, actor_id=str(current_user.id))

    resume = await db.get(Resume, app.resume_id)
    if not resume or not resume.parsed_json:
        raise HTTPException(status_code=404, detail="简历不存在或无法解析")

    # 新审计绑定当前 application resume version；历史记录保存当次不可变快照。
    snapshot = get_resume_snapshot(app)
    if not snapshot or not snapshot.get("parsed_json"):
        raise HTTPException(status_code=409, detail="该申请没有可用的简历版本快照")
    resume = _SnapshotResume(resume, snapshot["parsed_json"])

    return await _credibility_audit_response(
        db,
        employer=current_user,
        job=job,
        resume=resume,
        application=app,
        resume_snapshot=snapshot,
        idempotency_key=idempotency_key,
    )


@router.post("/{application_id}/mark-reviewed")
async def mark_application_reviewed_endpoint(
    application_id: str,
    req: Optional[ReviewRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """招聘方标记申请/claim 已复核（持久化）。"""
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可复核")
    app = await db.get(JobApplication, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="申请不存在")
    job = await db.get(JobDescription, app.job_id)
    if not job or job.employer_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权操作")
    if app.status in {"accepted", "rejected"}:
        raise HTTPException(status_code=409, detail="终态申请不能复核")

    body = req or ReviewRequest()
    try:
        if body.claim_id:
            from .claim_threads import mark_claim_reviewed

            mark_claim_reviewed(app, body.claim_id)
            passport_claim = await claim_for_source_key(db, str(app.resume_id), body.claim_id)
            if passport_claim:
                await mark_application_claim_reviewed(
                    db,
                    application_id=str(app.id),
                    claim_id=str(passport_claim.id),
                    employer_id=str(current_user.id),
                )
        else:
            mark_application_reviewed(app)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await db.commit()
    await db.refresh(app)
    return {"status": "ok", "application": _application_payload(app, job)}


@router.post("/{application_id}/claim-conflicts")
async def mark_application_claim_conflict_endpoint(
    application_id: str,
    body: ConflictReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Authorized employer records a discrepancy for follow-up, not a fraud verdict."""
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可记录复核冲突")
    app = await db.get(JobApplication, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="申请不存在或无权访问")
    job = await db.get(JobDescription, app.job_id)
    if not job or job.employer_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="申请不存在或无权访问")
    ensure_application_has_candidate_authorization(app)
    claim = await claim_for_source_key(db, str(app.resume_id), body.claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="主张不存在或不属于当前申请")
    await record_application_conflict(
        db,
        claim,
        application_id=str(app.id),
        employer_id=str(current_user.id),
        reason=body.reason,
    )
    await db.commit()
    return {
        "status": "conflict_recorded",
        "claim_id": str(claim.id),
        "message": "已记录待澄清冲突，不代表对事实作出判定。",
    }


@router.get("/{application_id}/events")
async def application_events_sse(
    application_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE：申请消息/澄清/面试事件准实时推送。"""
    app = await db.get(JobApplication, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="申请不存在")
    await _ensure_participant(app, current_user)

    queue = await event_bus.subscribe_application(application_id)

    async def gen():
        try:
            async for chunk in sse_event_stream(queue):
                yield chunk
        finally:
            await event_bus.unsubscribe_application(application_id, queue)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/stream/me")
async def user_events_sse(
    current_user: User = Depends(get_current_user),
):
    """SSE：当前用户维度的申请事件（角标刷新）。"""
    user_id = str(current_user.id)
    queue = await event_bus.subscribe_user(user_id)

    async def gen():
        try:
            async for chunk in sse_event_stream(queue):
                yield chunk
        finally:
            await event_bus.unsubscribe_user(user_id, queue)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/feedback/audit-finding")
async def submit_audit_feedback(
    req: AuditFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """雇主对审计 finding 标注有用/误报（训练数据飞轮）。"""
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可反馈")
    label = (req.label or "").strip()
    if label not in {"useful", "false_positive", "unclear"}:
        raise HTTPException(status_code=400, detail="label 须为 useful / false_positive / unclear")

    record, application = await ensure_employer_can_submit_audit_feedback(
        db,
        employer_id=str(current_user.id),
        audit_record_id=req.audit_record_id,
        application_id=req.application_id,
        finding_id=req.finding_id,
        claim_id=req.claim_id,
    )

    # 脱敏：只保留结构字段；归属一律以服务端校验后的记录为准
    snapshot = None
    if isinstance(req.finding_snapshot, dict):
        snapshot = {
            k: req.finding_snapshot.get(k)
            for k in ("id", "claim_id", "severity", "signal_type", "title", "category")
            if k in req.finding_snapshot
        }

    resolved_application_id = (
        str(application.id)
        if application is not None
        else (str(record.application_id) if record.application_id else None)
    )

    fb = AuditFindingFeedback(
        audit_record_id=str(record.id),
        employer_id=str(current_user.id),
        application_id=resolved_application_id,
        claim_id=req.claim_id,
        finding_id=req.finding_id,
        finding_snapshot=snapshot,
        label=label,
        note=(req.note or "")[:500] or None,
    )
    db.add(fb)
    await db.commit()
    await db.refresh(fb)
    return {"status": "ok", "feedback_id": str(fb.id)}


@router.get("/{application_id}/audit-history")
async def application_audit_history(
    application_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可查看")
    app = await db.get(JobApplication, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="申请不存在")
    job = await db.get(JobDescription, app.job_id)
    if not job or job.employer_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权查看")

    stmt = (
        select(CredibilityAuditRecord)
        .where(CredibilityAuditRecord.application_id == application_id)
        .order_by(CredibilityAuditRecord.created_at.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    # PR15: employer-facing history omits risk_score; legacy DB values remain readable in DB only.
    return [
        _omit_risk_score(
            {
                "id": str(r.id),
                "overall_status": r.overall_status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "report": r.report,
                "legacy_risk_score_present": r.risk_score is not None,
            }
        )
        for r in records
    ]
