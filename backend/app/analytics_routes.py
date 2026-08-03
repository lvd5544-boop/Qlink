import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .database import get_db
from .models_db import User, Company, HiredProfileSubmission
from .company_registry import seed_companies, infer_role_family, TIER_LABELS
from .market_analytics import (
    get_company_profile,
    rebuild_hired_benchmarks_statistical,
)
from .resume_coach_service import run_resume_coach
from .fairness import build_fairness_baseline
from .background_jobs import enqueue_job, shared_redis
from .security import owned_resume_or_404, require_admin, require_candidate

router = APIRouter(prefix="/analytics", tags=["数据分析"])


class HiredProfileSubmitRequest(BaseModel):
    company_id: str
    role_title: str
    school: Optional[str] = None
    degree: Optional[str] = None
    school_tier: Optional[str] = None  # 985 / 211 / 双一流 / 其他
    skills: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    leadership_examples: List[str] = Field(default_factory=list)
    hired_year: Optional[int] = None


class ResumeCoachRequest(BaseModel):
    resume_id: str
    company_id: str
    role_family: Optional[str] = None
    target_job_title: Optional[str] = None


class ModerateSubmissionRequest(BaseModel):
    status: Literal["approved", "rejected"]


MAX_HIRED_SUBMISSIONS_PER_DAY = 2
MAX_SKILLS_PER_SUBMISSION = 25


def _validate_hired_submission(req: HiredProfileSubmitRequest) -> None:
    if len(req.skills or []) > MAX_SKILLS_PER_SUBMISSION:
        raise HTTPException(
            status_code=400,
            detail=f"技能条目过多（最多 {MAX_SKILLS_PER_SUBMISSION} 项）",
        )
    if len(req.soft_skills or []) > 15 or len(req.leadership_examples or []) > 10:
        raise HTTPException(status_code=400, detail="软实力或领导力条目过多，请精简")
    title = (req.role_title or "").strip()
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="职位名称过短")
    spam_markers = ["测试", "test", "asdf", "1111"]
    if any(m in title.lower() for m in spam_markers):
        raise HTTPException(status_code=400, detail="职位名称疑似无效，请填写真实岗位")


@router.get("/fairness/baseline")
async def fairness_baseline(
    top_k: int = 10,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Pilot fairness monitoring: score distributions and observational ratios.

    Does not collect or expose demographic attributes. Admin-only.
    """
    if top_k < 1 or top_k > 50:
        raise HTTPException(status_code=400, detail="top_k 需在 1-50 之间")
    return await build_fairness_baseline(db, top_k=top_k)


class FairnessLegalGroupRequest(BaseModel):
    top_k: int = 10
    legal_basis_attested: bool = False
    groups: List[dict] = Field(default_factory=list)


@router.post("/fairness/baseline")
async def fairness_baseline_with_legal_groups(
    body: FairnessLegalGroupRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Same baseline, optionally with operator-attested de-identified groups."""
    if body.top_k < 1 or body.top_k > 50:
        raise HTTPException(status_code=400, detail="top_k 需在 1-50 之间")
    if body.groups and not body.legal_basis_attested:
        raise HTTPException(
            status_code=400,
            detail="提交去标识化分组时必须确认 legal_basis_attested=true",
        )
    return await build_fairness_baseline(
        db,
        top_k=body.top_k,
        legal_groups=body.groups,
        legal_basis_attested=body.legal_basis_attested,
    )


@router.get("/companies")
async def list_companies(
    tier: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Company).order_by(Company.tier, Company.name)
    if tier:
        stmt = stmt.where(Company.tier == tier)
    companies = (await db.execute(stmt)).scalars().all()
    if not companies:
        await seed_companies(db)
        companies = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "tier": c.tier,
            "tier_label": TIER_LABELS.get(c.tier, c.tier),
            "industry": c.industry,
            "aliases": c.name_aliases or [],
        }
        for c in companies
    ]


@router.get("/companies/{company_id}/profile")
async def company_profile(
    company_id: str,
    role_family: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = await get_company_profile(db, company_id, role_family)
    if not profile:
        raise HTTPException(status_code=404, detail="公司不存在")
    return profile


@router.post("/hired-profiles")
async def submit_hired_profile(
    req: HiredProfileSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "candidate":
        raise HTTPException(status_code=403, detail="仅求职者可提交录用画像")

    company = await db.get(Company, req.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="公司不存在")

    _validate_hired_submission(req)

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    dup = (
        await db.execute(
            select(func.count())
            .select_from(HiredProfileSubmission)
            .where(
                HiredProfileSubmission.user_id == str(current_user.id),
                HiredProfileSubmission.company_id == req.company_id,
                HiredProfileSubmission.created_at >= week_ago,
            )
        )
    ).scalar() or 0
    if dup >= 3:
        raise HTTPException(
            status_code=429,
            detail="同一公司 7 天内提交过多，请等待审核或稍后再试",
        )

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_count = (
        await db.execute(
            select(func.count())
            .select_from(HiredProfileSubmission)
            .where(
                HiredProfileSubmission.user_id == str(current_user.id),
                HiredProfileSubmission.created_at >= since,
            )
        )
    ).scalar() or 0
    if recent_count >= MAX_HIRED_SUBMISSIONS_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail=f"24 小时内最多提交 {MAX_HIRED_SUBMISSIONS_PER_DAY} 条录用画像，请明日再试",
        )

    role_family = infer_role_family(req.role_title)
    auto_approve = os.getenv("ANALYTICS_AUTO_APPROVE_SUBMISSIONS", "").lower() in (
        "1",
        "true",
        "yes",
    )
    status = "approved" if auto_approve else "pending"

    submission = HiredProfileSubmission(
        user_id=str(current_user.id),
        company_id=req.company_id,
        role_title=req.role_title,
        role_family=role_family,
        school=req.school,
        degree=req.degree,
        school_tier=req.school_tier,
        skills=req.skills,
        soft_skills=req.soft_skills,
        leadership_examples=req.leadership_examples,
        hired_year=req.hired_year,
        status=status,
    )
    db.add(submission)
    await db.commit()

    if status == "approved":
        await rebuild_hired_benchmarks_statistical(db)
        msg = "已审核通过，将以极低权重（<12%）纳入统计，主要结论仍来自网络经验帖"
    else:
        msg = "已提交，待审核通过后才会以极低权重纳入统计（防止刷数据）"

    return {
        "msg": msg,
        "role_family": role_family,
        "status": status,
    }


@router.get("/hired-profiles/mine")
async def my_hired_submissions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(HiredProfileSubmission).where(
        HiredProfileSubmission.user_id == str(current_user.id)
    )
    rows = (await db.execute(stmt)).scalars().all()
    result = []
    for r in rows:
        company = await db.get(Company, r.company_id)
        result.append(
            {
                "id": r.id,
                "company_name": company.name if company else "",
                "role_title": r.role_title,
                "role_family": r.role_family,
                "school_tier": r.school_tier,
                "hired_year": r.hired_year,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return result


@router.patch("/hired-profiles/submissions/{submission_id}/moderate")
async def moderate_hired_submission(
    submission_id: str,
    body: ModerateSubmissionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """管理员审核用户提交的录用画像（通过/拒绝）。"""

    row = await db.get(HiredProfileSubmission, submission_id)
    if not row:
        raise HTTPException(status_code=404, detail="提交不存在")

    row.status = body.status
    await db.commit()
    if body.status == "approved":
        await rebuild_hired_benchmarks_statistical(db)

    return {"msg": f"已更新为 {body.status}", "id": submission_id}


@router.post("/resume-coach")
async def resume_coach(
    req: ResumeCoachRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_candidate),
):
    resume = await owned_resume_or_404(db, req.resume_id, current_user)
    return await run_resume_coach(
        db,
        actor=current_user,
        resume=resume,
        company_id=req.company_id,
        role_family=req.role_family,
        target_job_title=req.target_job_title,
        idempotency_key=idempotency_key or str(uuid.uuid4()),
        entrypoint="analytics",
    )


@router.post("/rebuild")
async def rebuild_analytics(
    current_user: User = Depends(require_admin),
):
    """Enqueue analytics rebuild (admin)."""
    accepted = await enqueue_job(
        shared_redis(),
        job_type="analytics_rebuild",
        payload={"seed_companies": True},
        idempotency_key=f"analytics_rebuild:{current_user.id}",
    )
    return {
        "msg": "分析数据重建任务已受理",
        "job_id": accepted["job_id"],
        "status": accepted["status"],
    }


@router.post("/sync-forum-insights")
async def sync_forum_insights(
    current_user: User = Depends(require_admin),
):
    """Enqueue forum scrape + hired benchmark rebuild (admin)."""
    accepted = await enqueue_job(
        shared_redis(),
        job_type="forum_sync",
        payload={},
        idempotency_key=f"forum_sync:{current_user.id}",
    )
    return {
        "msg": "网络经验同步任务已受理",
        "job_id": accepted["job_id"],
        "status": accepted["status"],
    }


@router.get("/data-sources")
async def list_data_sources(current_user: User = Depends(get_current_user)):
    return {
        "methodology": (
            "公开招聘偏好：来自国企/外企岗位 JD 聚合。"
            "录用画像：仅使用公开可访问帖（不爬登录态、不绕过验证码），经否定句过滤、"
            "帖子分类、公司实体匹配后统计；展示需 ≥10 帖，较可信 ≥30 帖，较稳定 ≥100 帖；"
            "用户提交默认待审核，通过后权重上限 12%。"
        ),
        "sample_thresholds": {
            "display": 10,
            "credible": 30,
            "stable": 100,
        },
        "sources": [
            {
                "id": "jd_soe",
                "name": "国企公开招聘（JD）",
                "description": "国资央企招聘平台岗位描述聚合",
                "tier_filter": "soe",
                "layer": "D",
            },
            {
                "id": "jd_foreign",
                "name": "外企公开招聘（JD）",
                "description": "Remotive、Arbeitnow、Remote OK；配置免费 API Key 后还可同步 USAJOBS 当前公开岗位",
                "tier_filter": "foreign",
                "layer": "D",
            },
            {
                "id": "forum_statistical",
                "name": "网络录用经验（统计模型）",
                "description": "招聘论坛/社区公开帖统计；E 层定性线索，不得作为企业录用画像或正式筛选权重",
                "tier_filter": None,
                "layer": "E",
                "formal_profile_allowed": False,
            },
            {
                "id": "fortune500",
                "name": "世界500强对标库",
                "description": "500 强及别名用于公司匹配",
                "tier_filter": "fortune500",
                "layer": "C",
            },
        ],
        "planned_sources": [
            {"name": "ESCO v1.2.1", "status": "许可可用，待版本化导入", "note": "欧盟官方多语言职业/技能分类；记录版本与 attribution"},
            {"name": "O*NET Database", "status": "CC BY 4.0，待 attribution 实现", "note": "职业任务、技能与工作活动；不得改写成企业要求"},
            {"name": "BLS OEWS", "status": "官方统计，待 SOC crosswalk", "note": "职业就业与薪资统计，只用于市场背景"},
            {"name": "USAJOBS Historic JOA", "status": "公开 API，待增量管道", "note": "历史政府职位数据，用于岗位趋势而非当前招聘"},
            {"name": "高校就业质量报告", "status": "待逐校许可与结构评估", "note": "只使用官方公开 PDF/网页并保留页码引用"},
        ],
        "compliance": [
            "仅抓取公开可访问内容",
            "不爬登录态、不绕过验证码",
            "不采集私人信息；用户提交默认待审核",
        ],
    }
