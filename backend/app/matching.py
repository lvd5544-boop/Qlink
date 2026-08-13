import logging
from typing import List, Optional, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .models_db import Resume, JobDescription, MatchResult
from .matching_hybrid import hybrid_score_v2, build_match_reason_v2
from .matching_preference import apply_preference_policy
from .matching_rerank import llm_rerank_match

logger = logging.getLogger(__name__)


async def fetch_all_resumes(db: AsyncSession) -> List[Resume]:
    result = await db.execute(select(Resume))
    return result.scalars().all()


async def fetch_all_jobs(db: AsyncSession) -> List[JobDescription]:
    result = await db.execute(select(JobDescription))
    return [
        job
        for job in result.scalars().all()
        if (job.parsed_json or {}).get("_publication_status") != "draft"
        and not (job.parsed_json or {}).get("advisor_private")
    ]


def rule_based_filter(resume_json: dict, job_json: dict) -> bool:
    resume_location = resume_json.get("location_preference", "")
    job_location = job_json.get("location", "")
    if resume_location and job_location:
        if "远程" in resume_location:
            return True
        if job_location in resume_location or resume_location in job_location:
            return True
        return False
    return True


def evaluate_hybrid_match(
    resume_json: dict, job_json: dict, job_title: str
) -> tuple[float, dict, str]:
    """Human-first v3: selection policy first, statistical dimensions second."""
    score, breakdown, potential, tier = hybrid_score_v2(resume_json, job_json, job_title)
    base_score = score
    breakdown["potential_score"] = potential
    breakdown["match_tier"] = tier
    breakdown["improvement_delta"] = round(potential - score, 1)
    base_reason = build_match_reason_v2(breakdown, score)
    score, breakdown, policy_reason = apply_preference_policy(
        resume_json, job_json, job_title, score, breakdown
    )
    if (breakdown.get("preference_policy") or {}).get("eligible"):
        reason = f"{policy_reason}。{base_reason}"
    else:
        reason = policy_reason
    breakdown["match_tier"] = "high" if score >= 8 else ("medium" if score >= 5 else "low")
    eligible = (breakdown.get("preference_policy") or {}).get("eligible", True)
    breakdown["potential_score"] = (
        min(10.0, round(score + max(float(potential) - float(base_score), 0), 1))
        if eligible
        else score
    )
    breakdown["improvement_delta"] = round(breakdown["potential_score"] - score, 1)
    return score, breakdown, reason


# Backward-compatible alias for the existing unit tests and any local callers.
_evaluate_hybrid = evaluate_hybrid_match


async def _apply_llm_rerank(
    match: MatchResult,
    profile: dict,
    jd: dict,
    job_title: str,
) -> None:
    hybrid = float(match.score)
    breakdown = dict(match.score_breakdown or {})
    new_score, reason, llm_meta = await llm_rerank_match(profile, jd, job_title, hybrid, breakdown)
    breakdown["llm_rerank"] = llm_meta
    breakdown["hybrid_score_before_rerank"] = hybrid
    match.score = new_score
    match.reason = reason
    match.score_breakdown = breakdown


async def generate_matches(
    db: AsyncSession,
    resume_id: Optional[str] = None,
    job_id: Optional[str] = None,
    *,
    force_refresh: bool = False,
    llm_rerank_top: int = 0,
    use_llm: bool = False,  # 兼容旧参数：True 等价于 llm_rerank_top=5
):
    """
    生成/更新匹配记录。

    - 默认使用 hybrid v2 评分并写入 score_breakdown
    - force_refresh=True：已有记录也重新计算 hybrid
    - llm_rerank_top=N：对每个 resume 分数最高的 N 条做 LLM 重排
    """
    if use_llm and llm_rerank_top == 0:
        llm_rerank_top = 5

    resumes = await fetch_all_resumes(db)
    jobs = await fetch_all_jobs(db)
    if resume_id:
        resumes = [r for r in resumes if str(r.id) == resume_id]
    if job_id:
        jobs = [j for j in jobs if str(j.id) == job_id]

    job_map = {str(j.id): j for j in jobs}
    matches_by_resume: Dict[str, List[MatchResult]] = {}

    for resume in resumes:
        profile = resume.parsed_json or {}
        rid = str(resume.id)
        matches_by_resume[rid] = []

        for job in jobs:
            jd = job.parsed_json or {}
            if not rule_based_filter(profile, jd):
                continue

            existing = await db.execute(
                select(MatchResult).where(
                    MatchResult.resume_id == resume.id,
                    MatchResult.job_id == job.id,
                )
            )
            existing_match = existing.scalars().first()

            if existing_match and not force_refresh:
                if (existing_match.score_breakdown or {}).get("source") == "human_preference_v3":
                    matches_by_resume[rid].append(existing_match)
                    continue

            score, breakdown, reason = evaluate_hybrid_match(profile, jd, job.title)

            if existing_match:
                existing_match.score = score
                existing_match.reason = reason
                existing_match.score_breakdown = breakdown
                match_row = existing_match
            else:
                match_row = MatchResult(
                    resume_id=resume.id,
                    job_id=job.id,
                    score=score,
                    reason=reason,
                    score_breakdown=breakdown,
                )
                db.add(match_row)

            matches_by_resume[rid].append(match_row)

    await db.flush()

    if llm_rerank_top > 0:
        for resume in resumes:
            rid = str(resume.id)
            profile = resume.parsed_json or {}
            eligible_matches = [
                value
                for value in matches_by_resume.get(rid, [])
                if (value.score_breakdown or {}).get("preference_policy", {}).get("eligible", True)
            ]
            ranked = sorted(eligible_matches, key=lambda m: m.score, reverse=True)
            for match in ranked[:llm_rerank_top]:
                job = job_map.get(str(match.job_id))
                if not job:
                    job = await db.get(JobDescription, match.job_id)
                if job:
                    await _apply_llm_rerank(match, profile, job.parsed_json or {}, job.title)

    await db.commit()


async def generate_matches_for_user(
    db: AsyncSession,
    user_id: str,
    *,
    force_refresh: bool = True,
    llm_rerank_top: int = 5,
) -> int:
    """为某用户所有简历生成匹配（前端刷新用）。"""
    stmt = select(Resume).where(Resume.user_id == user_id)
    result = await db.execute(stmt)
    resumes = result.scalars().all()
    for resume in resumes:
        await generate_matches(
            db,
            resume_id=str(resume.id),
            force_refresh=force_refresh,
            llm_rerank_top=llm_rerank_top,
        )
    return len(resumes)


async def generate_matches_auto(llm_rerank_top: int = 20):
    """定时任务：全量 hybrid + Top-K LLM 重排。"""
    from .database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        resumes = await fetch_all_resumes(db)
        logger.info("Cron match: %d resumes, llm_rerank_top=%d", len(resumes), llm_rerank_top)
        for resume in resumes:
            await generate_matches(
                db,
                resume_id=str(resume.id),
                force_refresh=True,
                llm_rerank_top=llm_rerank_top,
            )
