#!/usr/bin/env python3
"""Seed, verify, and narrowly clean isolated PR3 browser-smoke data."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import sys
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

database_url = os.getenv("DATABASE_URL", "").strip()
if not database_url or "jobplatform_test" not in (make_url(database_url).database or ""):
    raise SystemExit("Refusing UI smoke data operation: DATABASE_URL must contain jobplatform_test")

from app.application_state import capture_resume_snapshot, set_application_status  # noqa: E402
from app.auth import get_password_hash  # noqa: E402
from app.claim_threads import open_claim_thread  # noqa: E402
from app.database import engine  # noqa: E402
from app.models_db import (  # noqa: E402
    ApplicationMessage,
    AuditFindingFeedback,
    CredibilityAuditRecord,
    InterviewInvitation,
    JobApplication,
    JobDescription,
    MatchResult,
    Resume,
    UsageEvent,
    User,
)


def _resume_json(name: str, suffix: str) -> dict:
    return {
        "name": name,
        "email": f"pr3-{suffix}@example.invalid",
        "expected_job_title": "后端工程师",
        "summary": "负责高并发订单平台，主导核心模块并显著提升性能",
        "skills": [{"name": "Python"}, {"name": "PostgreSQL"}],
        "work_experience": [
            {
                "company": "PR3 Test Corp",
                "position": "工程师",
                "duration_years": 2,
                "description": "主导订单系统重构，性能提升300%，覆盖全部核心接口",
            }
        ],
        "projects": [
            {
                "name": "订单平台",
                "role": "核心负责人",
                "description": "负责架构升级与性能优化",
            }
        ],
    }


def _masked(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:8]}…@{domain}"


async def seed(output_path: Path) -> None:
    run_id = uuid.uuid4().hex[:10]
    password = f"Pr3Ui-{secrets.token_urlsafe(12)}"
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + f"-{run_id}"
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        employer = User(
            email=f"pr3-ui-employer-{suffix}@test.local",
            password_hash=get_password_hash(password),
            role="employer",
        )
        other_employer = User(
            email=f"pr3-ui-other-employer-{suffix}@test.local",
            password_hash=get_password_hash(password),
            role="employer",
        )
        candidate = User(
            email=f"pr3-ui-candidate-{suffix}@test.local",
            password_hash=get_password_hash(password),
            role="candidate",
        )
        pool_candidate = User(
            email=f"pr3-ui-pool-{suffix}@test.local",
            password_hash=get_password_hash(password),
            role="candidate",
        )
        db.add_all([employer, other_employer, candidate, pool_candidate])
        await db.flush()

        job_main = JobDescription(
            employer_id=str(employer.id),
            title=f"PR3 UI 主流程 {run_id}",
            raw_text="PR3 UI main flow",
            parsed_json={
                "title": f"PR3 UI 主流程 {run_id}",
                "description": "Python PostgreSQL 后端岗位",
                "required_skills": ["Python", "PostgreSQL"],
                "location": "测试环境",
            },
        )
        job_close = JobDescription(
            employer_id=str(employer.id),
            title=f"PR3 UI 人工关闭 {run_id}",
            raw_text="PR3 UI close flow",
            parsed_json={
                "title": f"PR3 UI 人工关闭 {run_id}",
                "description": "人工关闭澄清验收岗位",
                "required_skills": ["Python"],
                "location": "测试环境",
            },
        )
        job_other = JobDescription(
            employer_id=str(other_employer.id),
            title=f"PR3 UI 其他租户 {run_id}",
            raw_text="PR3 UI other tenant",
            parsed_json={"title": f"PR3 UI 其他租户 {run_id}", "location": "测试环境"},
        )
        db.add_all([job_main, job_close, job_other])
        await db.flush()

        resume_initial = Resume(
            user_id=str(candidate.id),
            raw_text="PR3 UI initial resume",
            parsed_json=_resume_json("PR3 Candidate Initial", f"initial-{run_id}"),
        )
        resume_other = Resume(
            user_id=str(candidate.id),
            raw_text="PR3 UI alternate resume",
            parsed_json=_resume_json("PR3 Candidate Alternate", f"alternate-{run_id}"),
        )
        pool_resume = Resume(
            user_id=str(pool_candidate.id),
            raw_text="PR3 UI unauthorized pool resume",
            parsed_json=_resume_json("PR3 Pool Candidate", f"pool-{run_id}"),
        )
        db.add_all([resume_initial, resume_other, pool_resume])
        await db.flush()

        app_main = JobApplication(
            job_id=str(job_main.id),
            employer_id=str(employer.id),
            candidate_id=str(candidate.id),
            resume_id=str(resume_initial.id),
            status="submitted",
            cover_letter="PR3 UI 主流程申请",
            pipeline_meta={},
        )
        capture_resume_snapshot(
            app_main,
            resume_initial,
            actor_id=str(candidate.id),
            source="candidate_applied",
        )
        app_close = JobApplication(
            job_id=str(job_close.id),
            employer_id=str(employer.id),
            candidate_id=str(candidate.id),
            resume_id=str(resume_initial.id),
            status="submitted",
            cover_letter="PR3 UI 人工关闭申请",
            pipeline_meta={},
        )
        capture_resume_snapshot(
            app_close,
            resume_initial,
            actor_id=str(candidate.id),
            source="candidate_applied",
        )
        app_other = JobApplication(
            job_id=str(job_other.id),
            employer_id=str(other_employer.id),
            candidate_id=str(candidate.id),
            resume_id=str(resume_initial.id),
            status="submitted",
            cover_letter="PR3 UI 跨租户申请",
            pipeline_meta={},
        )
        capture_resume_snapshot(
            app_other,
            resume_initial,
            actor_id=str(candidate.id),
            source="candidate_applied",
        )
        db.add_all([app_main, app_close, app_other])
        await db.flush()

        close_message = ApplicationMessage(
            application_id=str(app_close.id),
            sender_id=str(employer.id),
            body="[澄清请求]\n关于 claim：「人工关闭测试 Claim」\n请补充说明：请说明验证细节",
            message_kind="clarification_request",
            message_meta={
                "claim_id": "ui_close_claim",
                "claim_text": "人工关闭测试 Claim",
                "questions": ["请说明验证细节"],
            },
        )
        db.add(close_message)
        await db.flush()
        open_claim_thread(
            app_close,
            claim_id="ui_close_claim",
            claim_text="人工关闭测试 Claim",
            request_message_id=str(close_message.id),
            questions=["请说明验证细节"],
        )
        set_application_status(
            app_close,
            "needs_clarification",
            action="create_claim_request",
            actor_role="employer",
            actor_id=str(employer.id),
            source="ui_smoke_seed",
        )

        match = MatchResult(
            resume_id=str(pool_resume.id),
            job_id=str(job_main.id),
            score=8.1,
            reason="PR3 UI unauthorized pool recommendation",
            score_breakdown={"skills": 8},
        )
        db.add(match)
        await db.commit()

    state = {
        "run_id": run_id,
        "database": make_url(database_url).database,
        "password": password,
        "employer_email": employer.email,
        "other_employer_email": other_employer.email,
        "candidate_email": candidate.email,
        "pool_candidate_email": pool_candidate.email,
        "ids": {
            "users": [
                str(employer.id),
                str(other_employer.id),
                str(candidate.id),
                str(pool_candidate.id),
            ],
            "jobs": [str(job_main.id), str(job_close.id), str(job_other.id)],
            "resumes": [
                str(resume_initial.id),
                str(resume_other.id),
                str(pool_resume.id),
            ],
            "applications": [str(app_main.id), str(app_close.id), str(app_other.id)],
            "matches": [str(match.id)],
            "job_main": str(job_main.id),
            "job_close": str(job_close.id),
            "job_other": str(job_other.id),
            "app_main": str(app_main.id),
            "app_close": str(app_close.id),
            "app_other": str(app_other.id),
            "resume_initial": str(resume_initial.id),
            "resume_other": str(resume_other.id),
            "pool_resume": str(pool_resume.id),
        },
    }
    output_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"seeded run={run_id} database={state['database']}")
    print(f"employer={_masked(employer.email)} candidate={_masked(candidate.email)}")
    print(f"state_file={output_path}")
    await engine.dispose()


async def verify(state_path: Path) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    ids = state["ids"]
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        apps = list(
            (
                await db.execute(
                    select(JobApplication).where(JobApplication.id.in_(ids["applications"]))
                )
            ).scalars()
        )
        invitations = list(
            (
                await db.execute(
                    select(InterviewInvitation).where(
                        InterviewInvitation.application_id.in_(ids["applications"])
                    )
                )
            ).scalars()
        )
        duplicate_main = (
            await db.execute(
                select(func.count())
                .select_from(JobApplication)
                .where(
                    JobApplication.job_id == ids["job_main"],
                    JobApplication.candidate_id == apps[0].candidate_id,
                )
            )
        ).scalar_one()
    payload = {
        "applications": {
            str(app.id): {
                "status": app.status,
                "resume_is_initial": app.resume_id == ids["resume_initial"],
                "open_claims": sum(
                    1
                    for thread in ((app.pipeline_meta or {}).get("claim_threads") or {}).values()
                    if thread.get("status") == "open"
                ),
                "status_history_count": len((app.pipeline_meta or {}).get("status_history") or []),
            }
            for app in apps
        },
        "pending_invitation_count": sum(
            1 for invitation in invitations if invitation.status == "pending"
        ),
        "main_job_application_count": duplicate_main,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    await engine.dispose()


async def cleanup(state_path: Path) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    ids = state["ids"]
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        app_ids = ids["applications"]
        audit_ids = list(
            (
                await db.execute(
                    select(CredibilityAuditRecord.id).where(
                        CredibilityAuditRecord.application_id.in_(app_ids)
                    )
                )
            ).scalars()
        )
        if audit_ids:
            await db.execute(
                delete(AuditFindingFeedback).where(
                    AuditFindingFeedback.audit_record_id.in_(audit_ids)
                )
            )
        await db.execute(
            delete(AuditFindingFeedback).where(AuditFindingFeedback.application_id.in_(app_ids))
        )
        await db.execute(
            delete(CredibilityAuditRecord).where(CredibilityAuditRecord.application_id.in_(app_ids))
        )
        await db.execute(
            delete(ApplicationMessage).where(ApplicationMessage.application_id.in_(app_ids))
        )
        await db.execute(
            delete(InterviewInvitation).where(InterviewInvitation.application_id.in_(app_ids))
        )
        await db.execute(delete(JobApplication).where(JobApplication.id.in_(app_ids)))
        await db.execute(delete(MatchResult).where(MatchResult.id.in_(ids["matches"])))
        await db.execute(delete(Resume).where(Resume.id.in_(ids["resumes"])))
        await db.execute(delete(JobDescription).where(JobDescription.id.in_(ids["jobs"])))
        await db.execute(delete(UsageEvent).where(UsageEvent.user_id.in_(ids["users"])))
        await db.execute(delete(User).where(User.id.in_(ids["users"])))
        await db.commit()
        remaining = {
            "users": (
                await db.execute(
                    select(func.count()).select_from(User).where(User.id.in_(ids["users"]))
                )
            ).scalar_one(),
            "jobs": (
                await db.execute(
                    select(func.count())
                    .select_from(JobDescription)
                    .where(JobDescription.id.in_(ids["jobs"]))
                )
            ).scalar_one(),
            "resumes": (
                await db.execute(
                    select(func.count()).select_from(Resume).where(Resume.id.in_(ids["resumes"]))
                )
            ).scalar_one(),
            "applications": (
                await db.execute(
                    select(func.count())
                    .select_from(JobApplication)
                    .where(JobApplication.id.in_(ids["applications"]))
                )
            ).scalar_one(),
            "usage_events": (
                await db.execute(
                    select(func.count())
                    .select_from(UsageEvent)
                    .where(UsageEvent.user_id.in_(ids["users"]))
                )
            ).scalar_one(),
        }
        if any(remaining.values()):
            raise RuntimeError(f"UI smoke cleanup left residual rows: {remaining}")
    print(f"cleaned run={state['run_id']} database={state['database']}")
    await engine.dispose()


async def main_async(args: argparse.Namespace) -> None:
    state_path = Path(args.state_file)
    if args.command == "seed":
        await seed(state_path)
    elif args.command == "verify":
        await verify(state_path)
    else:
        await cleanup(state_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="PR3 isolated UI smoke data")
    parser.add_argument("command", choices=("seed", "verify", "cleanup"))
    parser.add_argument("--state-file", required=True)
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
