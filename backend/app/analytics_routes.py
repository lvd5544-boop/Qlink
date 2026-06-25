import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .database import get_db
from .models_db import User, Resume, Company, HiredProfileSubmission
from .company_registry import seed_companies, infer_role_family, TIER_LABELS
from .market_analytics import (
    get_company_profile,
    rebuild_market_insights,
    rebuild_hired_benchmarks_statistical,
    run_full_analytics_rebuild,
)
from .forum_insight_pipeline import sync_forum_insights_to_db
from .resume_coach import generate_resume_coach

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
    current_user: User = Depends(get_current_user),
):
    """招聘方审核用户提交的录用画像（通过/拒绝）"""
    if current_user.role != "employer":
        raise HTTPException(status_code=403, detail="仅招聘方可审核")

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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = await db.get(Resume, req.resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if str(resume.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该简历")

    try:
        result = await generate_resume_coach(
            db,
            resume.parsed_json or {},
            req.company_id,
            req.role_family,
            req.target_job_title,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"简历诊断失败: {e}")

    return result


@router.post("/rebuild")
async def rebuild_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动触发聚合（开发/管理员用）"""
    await seed_companies(db)
    forum_stats = await sync_forum_insights_to_db(db)
    jd_count = await rebuild_market_insights(db)
    hb_count = await rebuild_hired_benchmarks_statistical(db)
    return {
        "msg": "分析数据已重建（含网络论坛抓取与统计模型）",
        "forum": forum_stats,
        "market_insights": jd_count,
        "hired_benchmarks": hb_count,
    }


@router.post("/sync-forum-insights")
async def sync_forum_insights(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """抓取 Reddit / V2EX / HN 等公开经验帖并重建统计录用画像"""
    stats = await sync_forum_insights_to_db(db)
    hb = await rebuild_hired_benchmarks_statistical(db)
    return {"msg": "网络经验数据已同步", "forum": stats, "hired_benchmarks": hb}


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
            },
            {
                "id": "jd_foreign",
                "name": "外企公开招聘（JD）",
                "description": "Remotive、Arbeitnow 等国际岗位 JD 聚合",
                "tier_filter": "foreign",
            },
            {
                "id": "forum_statistical",
                "name": "网络录用经验（统计模型）",
                "description": "招聘论坛/社区公开帖 + 统计结论，非用户填报主导",
                "tier_filter": None,
            },
            {
                "id": "fortune500",
                "name": "世界500强对标库",
                "description": "500 强及别名用于公司匹配",
                "tier_filter": "fortune500",
            },
        ],
        "planned_sources": [
            {"name": "牛客网公开面经", "status": "规划中", "note": "需合规评估 robots/API"},
            {"name": "脉脉公开讨论", "status": "规划中", "note": "不爬登录态"},
            {"name": "知乎/小红书公开帖", "status": "规划中", "note": "仅公开页"},
            {"name": "高校就业质量报告", "status": "规划中", "note": "结构化 PDF/网页"},
            {"name": "企业校招官网 JD", "status": "规划中", "note": "与公开招聘偏好合并"},
        ],
        "compliance": [
            "仅抓取公开可访问内容",
            "不爬登录态、不绕过验证码",
            "不采集私人信息；用户提交默认待审核",
        ],
    }
