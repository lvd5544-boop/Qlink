"""申请/简历跨租户授权（PR1 最小可复用函数，非完整权限框架）。"""

from __future__ import annotations

from typing import Optional, Set, Tuple

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models_db import CredibilityAuditRecord, JobApplication, JobDescription, Resume


def _not_found(detail: str = "资源不存在或无权访问") -> HTTPException:
    """统一防枚举响应：不区分「不存在」与「无权限」。"""
    return HTTPException(status_code=404, detail=detail)


def application_has_candidate_authorization(application: JobApplication) -> bool:
    """
    在正式 visibility/consent 模型完成前，仅候选人真实投递或明确授权可授予访问。

    旧记录、MatchResult、employer sourced/invited 均默认不授权。
    """
    meta = application.pipeline_meta if isinstance(application.pipeline_meta, dict) else {}
    source = meta.get("application_source")
    initial = meta.get("initial_submission_snapshot")
    if not source and isinstance(initial, dict):
        source = initial.get("source")
    return source in {"candidate_applied", "candidate_consented"}


def ensure_application_has_candidate_authorization(
    application: JobApplication,
) -> JobApplication:
    if not application_has_candidate_authorization(application):
        raise _not_found()
    return application


async def ensure_employer_can_access_resume_for_job(
    db: AsyncSession,
    *,
    employer_id: str,
    job_id: str,
    resume_id: str,
) -> Tuple[JobDescription, Resume, JobApplication]:
    """
    MVP 授权：招聘方拥有岗位，且存在 job_id+resume_id 精确申请，
    申请 employer_id 与岗位 owner 均为当前招聘方。

    MatchResult 不构成授权。失败一律 404。
    """
    job = await db.get(JobDescription, job_id)
    if not job or job.employer_id != str(employer_id):
        raise _not_found()

    app_stmt = (
        select(JobApplication)
        .where(
            JobApplication.job_id == str(job_id),
            JobApplication.resume_id == str(resume_id),
            JobApplication.employer_id == str(employer_id),
        )
        .order_by(JobApplication.created_at.desc())
    )
    app_result = await db.execute(app_stmt)
    application = app_result.scalars().first()
    if not application:
        raise _not_found()
    ensure_application_has_candidate_authorization(application)

    # 双保险：岗位 owner 与申请雇主一致
    if application.employer_id != str(employer_id) or job.employer_id != str(employer_id):
        raise _not_found()

    resume = await db.get(Resume, resume_id)
    if not resume or not resume.parsed_json:
        raise _not_found()

    return job, resume, application


def collect_report_identity_ids(report: Optional[dict]) -> Tuple[Set[str], Set[str]]:
    """
    从落库/返回报告中收集 finding_id 与 claim_id。

    当前结构说明：
    - findings[] 多为 category/issue/severity，常无稳定 id；
    - claim_reasoning 运行时用 claim_items，落库 redacted 可能是 items；
    - 若集合为空，调用方应跳过 id 成员校验，避免打断合法反馈。
    """
    finding_ids: Set[str] = set()
    claim_ids: Set[str] = set()
    if not isinstance(report, dict):
        return finding_ids, claim_ids

    for f in report.get("findings") or []:
        if not isinstance(f, dict):
            continue
        if f.get("id"):
            finding_ids.add(str(f["id"]))
        if f.get("claim_id"):
            claim_ids.add(str(f["claim_id"]))

    cr = report.get("claim_reasoning") or {}
    if isinstance(cr, dict):
        for key in ("claim_items", "items", "flagged_claims_detail"):
            for item in cr.get(key) or []:
                if not isinstance(item, dict):
                    continue
                cid = item.get("claim_id") or item.get("id")
                if cid:
                    claim_ids.add(str(cid))
                    finding_ids.add(str(cid))

    return finding_ids, claim_ids


async def ensure_employer_can_submit_audit_feedback(
    db: AsyncSession,
    *,
    employer_id: str,
    audit_record_id: Optional[str],
    application_id: Optional[str],
    finding_id: Optional[str] = None,
    claim_id: Optional[str] = None,
) -> Tuple[CredibilityAuditRecord, Optional[JobApplication]]:
    """
    反馈写入前校验：审计记录归属当前雇主；若带 application_id，
    则申请/岗位/简历须与审计记录一致。不信任客户端归属字段。
    """
    if not audit_record_id or not str(audit_record_id).strip():
        raise HTTPException(status_code=400, detail="缺少 audit_record_id")

    record = await db.get(CredibilityAuditRecord, str(audit_record_id).strip())
    if not record or record.employer_id != str(employer_id):
        raise _not_found()

    application: Optional[JobApplication] = None
    if application_id:
        application = await db.get(JobApplication, str(application_id))
        if not application or application.employer_id != str(employer_id):
            raise _not_found()
        if record.application_id and str(record.application_id) != str(application.id):
            raise _not_found()
        if str(application.job_id) != str(record.job_id):
            raise _not_found()
        if str(application.resume_id) != str(record.resume_id):
            raise _not_found()
        job = await db.get(JobDescription, application.job_id)
        if not job or job.employer_id != str(employer_id):
            raise _not_found()
        if str(job.id) != str(record.job_id):
            raise _not_found()

    finding_ids, claim_ids = collect_report_identity_ids(record.report)
    known = finding_ids | claim_ids
    if known:
        if finding_id and str(finding_id) not in known:
            raise _not_found("反馈项不存在或无权访问")
        if claim_id and str(claim_id) not in known:
            raise _not_found("反馈项不存在或无权访问")

    return record, application
