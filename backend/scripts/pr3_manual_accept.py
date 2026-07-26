#!/usr/bin/env python3
"""
PR3 人工验收脚本：自动注册账号、播种岗位/简历/申请，再对运行中的 API 做边界断言。

用法（推荐从仓库根目录）：
  ./scripts/pr3_manual_accept.sh

或：
  cd backend && .venv/bin/python scripts/pr3_manual_accept.py --api http://localhost:8000

依赖：本地已启动后端（uvicorn / docker compose），并与本脚本共用同一 DATABASE_URL。
不依赖 LLM。验收数据会留在库中，便于随后在 UI 继续点看。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# 加载 backend/.env，使 DATABASE_URL 与运行中的 uvicorn 一致
try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_ROOT / ".env")
except ImportError:
    pass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application_state import capture_resume_snapshot, set_application_status
from app.auth import create_access_token, get_password_hash
from app.claim_threads import open_claim_thread
from app.database import engine
from app.models_db import JobApplication, JobDescription, Resume, User


PASSWORD = "Pr3Accept!234"
PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""


@dataclass
class Ctx:
    api: str
    run_id: str
    employer: Optional[User] = None
    candidate: Optional[User] = None
    job: Optional[JobDescription] = None
    resume_a: Optional[Resume] = None
    resume_b: Optional[Resume] = None
    application: Optional[JobApplication] = None
    employer_token: str = ""
    candidate_token: str = ""
    results: list[CheckResult] = field(default_factory=list)

    def record(self, name: str, ok: bool, detail: str = "") -> bool:
        status = PASS if ok else FAIL
        self.results.append(CheckResult(name=name, status=status, detail=detail))
        mark = "✓" if ok else "✗"
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
        return ok


def _token_for(user: User) -> str:
    return create_access_token(data={"sub": str(user.id)})


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _sample_resume(name: str, title: str) -> dict:
    return {
        "name": name,
        "email": f"{name.lower().replace(' ', '')}@example.com",
        "expected_job_title": title,
        "summary": f"{name} PR3 验收简历",
        "skills": [{"name": "Python"}, {"name": "SQL"}],
        "work_experience": [
            {
                "company": f"{name} Corp",
                "position": "工程师",
                "duration_years": 2,
                "description": "负责订单模块开发与性能优化",
            }
        ],
        "projects": [],
    }


async def seed(ctx: Ctx) -> None:
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = f"{stamp}-{ctx.run_id[:8]}"

    async with session_factory() as db:
        employer = User(
            email=f"pr3-employer-{suffix}@test.local",
            password_hash=get_password_hash(PASSWORD),
            role="employer",
        )
        candidate = User(
            email=f"pr3-candidate-{suffix}@test.local",
            password_hash=get_password_hash(PASSWORD),
            role="candidate",
        )
        db.add_all([employer, candidate])
        await db.flush()

        job = JobDescription(
            employer_id=str(employer.id),
            title=f"PR3验收岗位-{suffix}",
            raw_text="PR3 manual accept job",
            parsed_json={
                "title": f"PR3验收岗位-{suffix}",
                "required_skills": ["Python", "SQL"],
                "description": "人工验收用岗位",
                "location": "上海",
            },
        )
        db.add(job)
        await db.flush()

        resume_a = Resume(
            user_id=str(candidate.id),
            raw_text="PR3 resume A",
            parsed_json=_sample_resume("PR3CandA", "后端工程师"),
        )
        resume_b = Resume(
            user_id=str(candidate.id),
            raw_text="PR3 resume B",
            parsed_json=_sample_resume("PR3CandB", "后端工程师"),
        )
        db.add_all([resume_a, resume_b])
        await db.flush()

        application = JobApplication(
            job_id=str(job.id),
            employer_id=str(employer.id),
            candidate_id=str(candidate.id),
            resume_id=str(resume_a.id),
            status="submitted",
            cover_letter="PR3 验收投递",
            pipeline_meta={},
        )
        db.add(application)
        await db.flush()
        capture_resume_snapshot(
            application,
            resume_a,
            actor_id=str(candidate.id),
            source="candidate_applied",
        )
        open_claim_thread(
            application,
            claim_id="work_experience_0_action_0",
            claim_text="负责订单模块开发与性能优化",
            request_message_id="pr3-msg-1",
            questions=["请补充可验证的性能指标？"],
        )
        open_claim_thread(
            application,
            claim_id="work_experience_0_action_1",
            claim_text="负责订单模块开发与性能优化",
            request_message_id="pr3-msg-2",
            questions=["该优化覆盖哪些接口？"],
        )
        set_application_status(
            application,
            "needs_clarification",
            action="create_claim_request",
            actor_role="employer",
            actor_id=str(employer.id),
            source="manual_accept_seed",
        )
        await db.commit()

        ctx.employer = employer
        ctx.candidate = candidate
        ctx.job = job
        ctx.resume_a = resume_a
        ctx.resume_b = resume_b
        ctx.application = application
        ctx.employer_token = _token_for(employer)
        ctx.candidate_token = _token_for(candidate)

    print("播种完成：")
    print(f"  employer : {ctx.employer.email} / {PASSWORD}")
    print(f"  candidate: {ctx.candidate.email} / {PASSWORD}")
    print(f"  job_id   : {ctx.job.id}")
    print(f"  app_id   : {ctx.application.id}")
    print(f"  resume_a : {ctx.resume_a.id}")
    print(f"  resume_b : {ctx.resume_b.id}")
    print(f"  UI 申请页: /employer/applications/{ctx.job.id}")
    print()


async def expect_status(
    client: httpx.AsyncClient,
    *,
    method: str,
    path: str,
    token: str,
    json_body: Any,
    expect: set[int],
    name: str,
    ctx: Ctx,
) -> Optional[httpx.Response]:
    res = await client.request(
        method,
        path,
        headers=_headers(token),
        json=json_body,
    )
    ok = res.status_code in expect
    detail = f"HTTP {res.status_code}"
    if not ok:
        try:
            body = res.json()
            detail += f" body={json.dumps(body, ensure_ascii=False)[:200]}"
        except Exception:
            detail += f" text={res.text[:200]}"
    ctx.record(name, ok, detail)
    return res if ok else None


async def run_checks(ctx: Ctx) -> None:
    app_id = str(ctx.application.id)
    job_id = str(ctx.job.id)
    resume_a = str(ctx.resume_a.id)
    resume_b = str(ctx.resume_b.id)

    # Local smoke must ignore HTTP(S)_PROXY; otherwise localhost can return 502.
    async with httpx.AsyncClient(base_url=ctx.api, timeout=30.0, trust_env=False) as client:
        health = await client.get("/health")
        ctx.record("API /health 可达", health.status_code == 200, f"HTTP {health.status_code}")
        if health.status_code != 200:
            return

        print("\n== 7.1 状态机：通用 PATCH 不得直设业务状态 ==")
        for status in (
            "needs_clarification",
            "clarified",
            "clarification_closed",
            "interview_invited",
        ):
            await expect_status(
                client,
                method="PATCH",
                path=f"/applications/{app_id}/status",
                token=ctx.employer_token,
                json_body={"status": status},
                expect={403},
                name=f"招聘方 PATCH {status} → 403",
                ctx=ctx,
            )

        for status in ("viewed", "clarified", "accepted", "rejected"):
            await expect_status(
                client,
                method="PATCH",
                path=f"/applications/{app_id}/status",
                token=ctx.candidate_token,
                json_body={"status": status},
                expect={400, 403, 422},
                name=f"候选人 PATCH {status} → 拒绝",
                ctx=ctx,
            )

        print("\n== 7.1 招聘方显式人工关闭澄清 ==")
        close_res = await expect_status(
            client,
            method="POST",
            path=f"/applications/{app_id}/clarification/close",
            token=ctx.employer_token,
            json_body={"reason": "PR3 人工验收：长期未回复"},
            expect={200},
            name="POST clarification/close → 200",
            ctx=ctx,
        )
        if close_res is not None:
            body = close_res.json()
            ctx.record(
                "关闭后 status=clarification_closed",
                body.get("application", {}).get("status") == "clarification_closed",
                f"status={body.get('application', {}).get('status')}",
            )
            ctx.record(
                "关闭后 open_claim_count=0",
                body.get("open_claim_count") == 0,
                f"open={body.get('open_claim_count')}",
            )
            threads = body.get("claim_threads") or []
            closed_ok = bool(threads) and all(t.get("status") == "closed" for t in threads)
            has_audit = bool(threads) and all(
                t.get("closed_by") and t.get("close_reason") for t in threads
            )
            ctx.record("所有 Claim 标记为 closed", closed_ok, f"n={len(threads)}")
            ctx.record("关闭留痕含 closed_by/close_reason", has_audit)

        await expect_status(
            client,
            method="POST",
            path=f"/applications/{app_id}/clarification/close",
            token=ctx.employer_token,
            json_body={"reason": "再次关闭"},
            expect={400},
            name="无开放 Claim 时再关闭 → 400",
            ctx=ctx,
        )
        await expect_status(
            client,
            method="POST",
            path=f"/applications/{app_id}/clarification/close",
            token=ctx.candidate_token,
            json_body={"reason": "候选人不应能关"},
            expect={403},
            name="候选人关闭澄清 → 403",
            ctx=ctx,
        )

        print("\n== 7.2 申请 resume_id 不可静默变更 ==")
        dup = await expect_status(
            client,
            method="POST",
            path="/applications",
            token=ctx.candidate_token,
            json_body={"job_id": job_id, "resume_id": resume_b},
            expect={200},
            name="重复申请换简历 → 200 exists",
            ctx=ctx,
        )
        if dup is not None:
            payload = dup.json()
            ctx.record(
                "重复申请不改 resume_id",
                payload.get("application", {}).get("resume_id") == resume_a,
                f"resume_id={payload.get('application', {}).get('resume_id')}",
            )
            ctx.record(
                "提示需显式换简历",
                payload.get("resume_change_required_explicit") is True
                or payload.get("status") == "exists",
                f"status={payload.get('status')} flag={payload.get('resume_change_required_explicit')}",
            )

        await expect_status(
            client,
            method="POST",
            path=f"/applications/job/{job_id}/resume/{resume_b}/clarification-requests",
            token=ctx.employer_token,
            json_body={"claim_text": "某主张", "questions": ["请补充？"]},
            expect={409},
            name="人才池用另一份简历澄清 → 409",
            ctx=ctx,
        )

        await expect_status(
            client,
            method="PATCH",
            path=f"/applications/{app_id}/resume",
            token=ctx.candidate_token,
            json_body={"resume_id": resume_b, "confirm": False},
            expect={400},
            name="显式换简历无 confirm → 400",
            ctx=ctx,
        )
        change = await expect_status(
            client,
            method="PATCH",
            path=f"/applications/{app_id}/resume",
            token=ctx.candidate_token,
            json_body={"resume_id": resume_b, "confirm": True, "reason": "PR3验收换简历"},
            expect={409},
            name="已有招聘方活动后显式换简历 → 409",
            ctx=ctx,
        )

        print("\n== 7.1 面试邀请才进入 interview_invited ==")
        # 已有招聘方活动后换简历被拒绝，邀请必须继续使用当前 resume_a。
        invite = await expect_status(
            client,
            method="POST",
            path="/invitations/send",
            token=ctx.employer_token,
            json_body={
                "job_id": job_id,
                "resume_id": resume_a,
                "application_id": app_id,
                "message": "PR3 验收邀请",
            },
            expect={200},
            name="邀请接口成功 → 200",
            ctx=ctx,
        )
        if invite is not None:
            body = invite.json()
            ctx.record(
                "邀请后 application_status=interview_invited",
                body.get("application_status") == "interview_invited",
                f"status={body.get('application_status')}",
            )

        # 用另一份 resume_b 再邀应冲突。
        await expect_status(
            client,
            method="POST",
            path="/invitations/send",
            token=ctx.employer_token,
            json_body={
                "job_id": job_id,
                "resume_id": resume_b,
                "application_id": app_id,
                "message": "错误简历应冲突",
            },
            expect={409},
            name="邀请指定另一份简历 → 409",
            ctx=ctx,
        )

        # 直设 interview_invited 仍应失败
        await expect_status(
            client,
            method="PATCH",
            path=f"/applications/{app_id}/status",
            token=ctx.employer_token,
            json_body={"status": "interview_invited"},
            expect={403},
            name="邀请成功后仍不可 PATCH interview_invited",
            ctx=ctx,
        )


def print_summary(ctx: Ctx) -> int:
    passed = sum(1 for r in ctx.results if r.status == PASS)
    failed = sum(1 for r in ctx.results if r.status == FAIL)
    print("\n" + "=" * 56)
    print(f"PR3 人工验收结果：{passed} 通过 / {failed} 失败 / 共 {len(ctx.results)} 项")
    if failed:
        print("失败项：")
        for r in ctx.results:
            if r.status == FAIL:
                print(f"  - {r.name}: {r.detail}")
    else:
        print("全部通过。可登录以下账号在 UI 复核：")
        print(f"  招聘方 {ctx.employer.email} / {PASSWORD}")
        print(f"  候选人 {ctx.candidate.email} / {PASSWORD}")
        print(f"  申请页 /employer/applications/{ctx.job.id}")
    print("=" * 56)
    return 0 if failed == 0 else 1


async def main_async(api: str) -> int:
    ctx = Ctx(api=api.rstrip("/"), run_id=str(uuid.uuid4()))
    print(f"API: {ctx.api}")
    print(f"run: {ctx.run_id}\n")

    print("== 播种验收数据（直写 DB，不走 LLM） ==")
    try:
        await seed(ctx)
    except Exception as e:
        print(f"播种失败：{e}")
        print("请确认 DATABASE_URL 与正在运行的后端一致，且数据库可连。")
        return 2

    print("== 对运行中 API 执行验收断言 ==")
    try:
        await run_checks(ctx)
    except httpx.ConnectError:
        print(f"无法连接 {ctx.api}。请先启动后端：")
        print("  cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000")
        return 2

    return print_summary(ctx)


def main() -> None:
    parser = argparse.ArgumentParser(description="PR3 人工验收（自动播种 + HTTP 断言）")
    parser.add_argument(
        "--api",
        default="http://localhost:8000",
        help="后端 API 地址（默认 http://localhost:8000）",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args.api)))


if __name__ == "__main__":
    main()
