import logging
from collections import defaultdict
from typing import Dict, Optional, Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .company_registry import (
    seed_companies,
    match_company_by_name,
    match_companies_in_text,
    infer_role_family,
    extract_keywords_from_text,
    extract_school_tiers_from_text,
    increment_freq,
    top_n_freq,
    normalize_skill_name,
    SOFT_SKILL_KEYWORDS,
    LEADERSHIP_KEYWORDS,
    COMMUNICATION_KEYWORDS,
)
from .database import AsyncSessionLocal
from .models_db import (
    Company,
    JobDescription,
    MarketInsight,
    HiredProfileBenchmark,
    HiredProfileSubmission,
)
from .forum_insight_pipeline import load_extractions_grouped
from .statistical_benchmark import (
    aggregate_extractions_to_bucket,
    build_statistical_benchmark_payload,
    MAX_USER_SUBMISSION_WEIGHT_SHARE,
    MIN_FORUM_SAMPLES_DISPLAY,
    resolve_sample_tier,
    sample_tier_label,
)
from .insight_nlp import school_tier_disclaimer

logger = logging.getLogger(__name__)


def _job_full_text(parsed: dict, raw_title: str) -> str:
    parts = [raw_title or "", parsed.get("requirements") or ""]
    for r in parsed.get("responsibilities") or []:
        parts.append(str(r))
    parts.append(parsed.get("education") or "")
    parts.append(parsed.get("education_requirement") or "")
    return "\n".join(parts)


def _collect_from_job(parsed: dict, title: str) -> dict:
    text = _job_full_text(parsed, title)
    soft = list(parsed.get("soft_skills") or [])
    soft.extend(extract_keywords_from_text(text, SOFT_SKILL_KEYWORDS))
    leadership = list(parsed.get("leadership_signals") or [])
    leadership.extend(extract_keywords_from_text(text, LEADERSHIP_KEYWORDS))
    communication = list(parsed.get("communication_signals") or [])
    communication.extend(extract_keywords_from_text(text, COMMUNICATION_KEYWORDS))
    school_tiers = list(parsed.get("school_tier_keywords") or [])
    school_tiers.extend(extract_school_tiers_from_text(text))
    school_tiers.extend(extract_school_tiers_from_text(parsed.get("education") or ""))

    skills = []
    for s in parsed.get("required_skills") or []:
        if isinstance(s, dict):
            skills.append(s.get("name", ""))
        else:
            skills.append(str(s))

    edu = parsed.get("education_requirement") or parsed.get("education") or "未注明"

    return {
        "skills": skills,
        "education": edu,
        "school_tiers": school_tiers,
        "soft_skills": list(dict.fromkeys(soft)),
        "leadership": list(dict.fromkeys(leadership)),
        "communication": list(dict.fromkeys(communication)),
        "role_family": infer_role_family(parsed.get("title") or title),
    }


async def rebuild_market_insights(db: AsyncSession) -> int:
    """从 job_descriptions 聚合 JD 偏好并写入 market_insights"""
    companies = (await db.execute(select(Company))).scalars().all()
    if not companies:
        await seed_companies(db)
        companies = (await db.execute(select(Company))).scalars().all()

    jobs = (await db.execute(select(JobDescription))).scalars().all()

    buckets: Dict[tuple, dict] = defaultdict(
        lambda: {
            "jd_sample_size": 0,
            "skill_freq": {},
            "education_freq": {},
            "school_tier_freq": {},
            "soft_skill_freq": {},
            "leadership_freq": {},
            "communication_freq": {},
        }
    )

    for job in jobs:
        parsed = job.parsed_json or {}
        company_name = parsed.get("company_name") or ""
        job_text = _job_full_text(parsed, job.title) + "\n" + (job.raw_text or "")
        matched = []
        primary = match_company_by_name(company_name, companies)
        if primary:
            matched.append(primary)
        for c in match_companies_in_text(job_text, companies):
            if c not in matched:
                matched.append(c)
        if not matched:
            continue
        collected = _collect_from_job(parsed, job.title)
        for company in matched:
            key = (company.id, collected["role_family"])
            b = buckets[key]
            b["jd_sample_size"] += 1
            for sk in collected["skills"]:
                increment_freq(b["skill_freq"], normalize_skill_name(sk))
            increment_freq(b["education_freq"], collected["education"][:80])
            for st in collected["school_tiers"]:
                increment_freq(b["school_tier_freq"], st)
            for ss in collected["soft_skills"]:
                increment_freq(b["soft_skill_freq"], ss)
            for ls in collected["leadership"]:
                increment_freq(b["leadership_freq"], ls)
            for cs in collected["communication"]:
                increment_freq(b["communication_freq"], cs)

    await db.execute(delete(MarketInsight))
    written = 0
    for (company_id, role_family), data in buckets.items():
        insight = MarketInsight(
            company_id=company_id,
            role_family=role_family,
            jd_sample_size=data["jd_sample_size"],
            skill_freq=top_n_freq(data["skill_freq"]),
            education_freq=top_n_freq(data["education_freq"], 8),
            school_tier_freq=top_n_freq(data["school_tier_freq"]),
            soft_skill_freq=top_n_freq(data["soft_skill_freq"]),
            leadership_freq=top_n_freq(data["leadership_freq"]),
            communication_freq=top_n_freq(data["communication_freq"]),
        )
        db.add(insight)
        written += 1
    await db.commit()
    logger.info("Rebuilt %s market insights", written)
    return written


def _blend_user_submissions(
    bucket: dict, submissions: list, max_share: float = MAX_USER_SUBMISSION_WEIGHT_SHARE
) -> dict:
    """极低权重融合用户提交，避免偏差主导"""
    if not submissions:
        return bucket
    user_items = {
        "school_items": [],
        "skill_items": [],
        "soft_items": [],
        "leadership_items": [],
        "degree_items": [],
    }
    for sub in submissions:
        w = 0.15
        if sub.school_tier:
            user_items["school_items"].append((sub.school_tier, w))
        if sub.degree:
            user_items["degree_items"].append((sub.degree, w))
        for sk in sub.skills or []:
            user_items["skill_items"].append((normalize_skill_name(str(sk)), w))
        for ss in sub.soft_skills or []:
            user_items["soft_items"].append((str(ss), w))
        for le in sub.leadership_examples or []:
            user_items["leadership_items"].append((str(le), w))

    forum_eff = bucket.get("n_effective", 0) or 1
    cap = forum_eff * max_share / max(len(submissions), 1)
    for key in user_items:
        bucket[key].extend([(a, min(w, cap)) for a, w in user_items[key]])
    bucket["source_breakdown"]["user_submission"] = (
        bucket["source_breakdown"].get("user_submission", 0) + len(submissions) * cap
    )
    return bucket


async def rebuild_hired_benchmarks_statistical(db: AsyncSession) -> int:
    """基于网络论坛经验帖的统计模型构建录用画像（不以用户提交/JD 替代）"""
    grouped = await load_extractions_grouped(db)
    submissions_all = (
        (
            await db.execute(
                select(HiredProfileSubmission).where(HiredProfileSubmission.status == "approved")
            )
        )
        .scalars()
        .all()
    )
    sub_by_key = defaultdict(list)
    for s in submissions_all:
        sub_by_key[(s.company_id, s.role_family or "general")].append(s)

    await db.execute(delete(HiredProfileBenchmark))
    written = 0

    all_keys = set(grouped.keys()) | set(sub_by_key.keys())

    for key in all_keys:
        company_id, role_family = key
        extractions = grouped.get(key, [])

        bucket = aggregate_extractions_to_bucket(extractions)
        bucket = _blend_user_submissions(bucket, sub_by_key.get(key, []))

        payload = build_statistical_benchmark_payload(bucket)
        n_live = payload.get("n_samples_live", 0)
        n_corpus = payload.get("n_samples_corpus", 0)

        tier = resolve_sample_tier(payload["n_samples"], n_live=n_live)
        if tier == "insufficient":
            if n_corpus >= 1 and n_live == 0:
                notes = (
                    "当前仅有本地演示语料，不能作为真实统计依据；"
                    "下图仅供产品预览。请同步 Reddit/HN 等公开经验帖（展示≥10，较可信≥30，较稳定≥100）。"
                )
                source = "demo_preview"
            else:
                notes = (
                    f"真实网络经验帖不足（{n_live}<{MIN_FORUM_SAMPLES_DISPLAY}），"
                    "暂不输出统计录用画像；公开招聘偏好（JD）仍可在左侧查看。"
                    "请同步更多公开经验数据。"
                )
                source = "insufficient_forum"
        else:
            notes = "；".join(payload["statistical_conclusions"][:4])
            source = "statistical_forum"

        benchmark = HiredProfileBenchmark(
            company_id=company_id,
            role_family=role_family,
            school_tier_dist=payload["school_tier_dist"],
            skill_freq=payload["skill_freq"],
            soft_skill_freq=payload["soft_skill_freq"],
            leadership_freq=payload["leadership_freq"],
            degree_freq=payload["degree_freq"],
            source=source,
            n_samples=payload["n_samples"],
            notes=notes,
            confidence_score=payload["confidence_score"],
            source_breakdown=payload["source_breakdown"],
            statistical_summary={
                "conclusions": payload["statistical_conclusions"],
                "detail": payload["statistical_detail"],
                "n_effective_weight": payload["n_effective_weight"],
                "n_samples_live": payload.get("n_samples_live"),
                "n_samples_corpus": payload.get("n_samples_corpus"),
                "sample_tier": payload.get("sample_tier"),
                "sample_tier_label": sample_tier_label(payload.get("sample_tier", "")),
                "school_tier_disclaimer": school_tier_disclaimer(),
            },
            methodology=payload["methodology"],
        )
        db.add(benchmark)
        written += 1

    await db.commit()
    logger.info("Rebuilt %s statistical hired benchmarks", written)
    return written


async def run_full_analytics_rebuild():
    async with AsyncSessionLocal() as db:
        await seed_companies(db)
        await rebuild_market_insights(db)
        logger.info(
            "正式市场分析仅从岗位数据重建；E 层论坛内容不进入岗位画像或录用判断"
        )


def insight_to_dict(insight: MarketInsight) -> dict:
    return {
        "role_family": insight.role_family,
        "jd_sample_size": insight.jd_sample_size,
        "skill_freq": insight.skill_freq or {},
        "education_freq": insight.education_freq or {},
        "school_tier_freq": insight.school_tier_freq or {},
        "soft_skill_freq": insight.soft_skill_freq or {},
        "leadership_freq": insight.leadership_freq or {},
        "communication_freq": insight.communication_freq or {},
        "updated_at": insight.updated_at.isoformat() if insight.updated_at else None,
    }


def benchmark_to_dict(b: HiredProfileBenchmark) -> dict:
    return {
        "role_family": b.role_family,
        "school_tier_dist": b.school_tier_dist or {},
        "skill_freq": b.skill_freq or {},
        "soft_skill_freq": b.soft_skill_freq or {},
        "leadership_freq": b.leadership_freq or {},
        "degree_freq": b.degree_freq or {},
        "source": b.source,
        "n_samples": b.n_samples,
        "n_samples_live": (b.statistical_summary or {}).get("n_samples_live"),
        "notes": b.notes,
        "confidence_score": b.confidence_score,
        "source_breakdown": b.source_breakdown or {},
        "statistical_summary": b.statistical_summary or {},
        "sample_tier": (b.statistical_summary or {}).get("sample_tier"),
        "methodology": b.methodology,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


async def build_role_market_fallback(
    db: AsyncSession,
    role_family: str | None,
) -> dict[str, Any] | None:
    """Aggregate open JDs across companies when one company has too few samples."""

    if not role_family:
        return None
    jobs = (await db.execute(select(JobDescription))).scalars().all()
    bucket = {
        "jd_sample_size": 0,
        "skill_freq": {},
        "education_freq": {},
        "school_tier_freq": {},
        "soft_skill_freq": {},
        "leadership_freq": {},
        "communication_freq": {},
    }
    companies: set[str] = set()
    for job in jobs:
        parsed = job.parsed_json or {}
        collected = _collect_from_job(parsed, job.title)
        if collected["role_family"] != role_family:
            continue
        bucket["jd_sample_size"] += 1
        company_name = str(parsed.get("company_name") or "").strip()
        if company_name:
            companies.add(company_name)
        for skill in collected["skills"]:
            increment_freq(bucket["skill_freq"], normalize_skill_name(skill))
        increment_freq(bucket["education_freq"], collected["education"][:80])
        for key, values in (
            ("school_tier_freq", collected["school_tiers"]),
            ("soft_skill_freq", collected["soft_skills"]),
            ("leadership_freq", collected["leadership"]),
            ("communication_freq", collected["communication"]),
        ):
            for value in values:
                increment_freq(bucket[key], value)
    if not bucket["jd_sample_size"]:
        return None
    return {
        "role_family": role_family,
        "jd_sample_size": bucket["jd_sample_size"],
        "company_count": len(companies),
        "skill_freq": top_n_freq(bucket["skill_freq"]),
        "education_freq": top_n_freq(bucket["education_freq"], 8),
        "school_tier_freq": top_n_freq(bucket["school_tier_freq"]),
        "soft_skill_freq": top_n_freq(bucket["soft_skill_freq"]),
        "leadership_freq": top_n_freq(bucket["leadership_freq"]),
        "communication_freq": top_n_freq(bucket["communication_freq"]),
        "scope": "role_market_open_jd",
        "scope_label": "同岗位方向的跨公司公开 JD",
        "caveat": "这是岗位市场共性，不代表所选公司的招聘偏好。",
    }


async def get_company_profile(
    db: AsyncSession, company_id: str, role_family: Optional[str] = None
) -> Dict[str, Any]:
    company = await db.get(Company, company_id)
    if not company:
        return None

    mi_stmt = select(MarketInsight).where(MarketInsight.company_id == company_id)
    hb_stmt = select(HiredProfileBenchmark).where(HiredProfileBenchmark.company_id == company_id)
    if role_family:
        mi_stmt = mi_stmt.where(MarketInsight.role_family == role_family)
        hb_stmt = hb_stmt.where(HiredProfileBenchmark.role_family == role_family)

    insights = (await db.execute(mi_stmt)).scalars().all()
    benchmarks = (await db.execute(hb_stmt)).scalars().all()

    return {
        "company": {
            "id": company.id,
            "name": company.name,
            "tier": company.tier,
            "industry": company.industry,
        },
        "jd_insights": [insight_to_dict(i) for i in insights],
        "hired_benchmarks": [benchmark_to_dict(b) for b in benchmarks],
        "role_market_fallback": await build_role_market_fallback(db, role_family),
    }
