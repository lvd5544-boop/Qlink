"""论坛经验帖：抓取 → 清洗 → 抽取 → 入库"""

import logging
from collections import defaultdict

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .company_registry import seed_companies
from .forum_insight_fetcher import fetch_all_forum_posts, PLATFORM_WEIGHT
from .insight_text_processor import dedupe_posts, is_hiring_related
from .insight_extractor import extract_insights_from_post
from .models_db import ForumInsightPost, ForumInsightExtracted, Company

logger = logging.getLogger(__name__)


async def sync_forum_insights_to_db(db: AsyncSession) -> dict:
    await seed_companies(db)
    companies = (await db.execute(select(Company))).scalars().all()

    raw_posts = await fetch_all_forum_posts(companies)
    cleaned = dedupe_posts(raw_posts)
    hiring_posts = [p for p in cleaned if is_hiring_related(p.get("title", "") + p.get("body", ""))]

    await db.execute(delete(ForumInsightExtracted))
    await db.execute(delete(ForumInsightPost))

    post_count = 0
    extract_count = 0

    for p in hiring_posts:
        platform = p.get("platform", "unknown")
        p["platform_weight"] = PLATFORM_WEIGHT.get(platform, 0.8)
        row = ForumInsightPost(
            platform=platform,
            source_url=p.get("source_url"),
            content_hash=p["content_hash"],
            title=p.get("title"),
            body=p.get("body"),
            search_query=p.get("search_query"),
        )
        db.add(row)
        await db.flush()
        post_count += 1
        p["db_id"] = row.id

        for ex in extract_insights_from_post(p, companies):
            db.add(
                ForumInsightExtracted(
                    post_id=row.id,
                    company_id=ex["company_id"],
                    company_name_raw=ex["company_name_raw"],
                    role_family=ex["role_family"],
                    school_tier=ex.get("school_tier"),
                    degree=ex.get("degree"),
                    skills=ex.get("skills") or [],
                    soft_skills=ex.get("soft_skills") or [],
                    leadership_signals=ex.get("leadership_signals") or [],
                    platform=ex.get("platform"),
                    extraction_confidence=ex.get("extraction_confidence"),
                    weight=ex.get("weight"),
                    is_offer_story=1 if ex.get("is_offer_story") else 0,
                    post_type=ex.get("post_type") or "discussion",
                    recruitment_type=ex.get("recruitment_type") or "unknown",
                )
            )
            extract_count += 1

    await db.commit()
    logger.info("论坛入库: posts=%s extractions=%s", post_count, extract_count)
    return {"posts": post_count, "extractions": extract_count}


async def load_extractions_grouped(db: AsyncSession) -> dict:
    """按 (company_id, role_family) 分组提取记录"""
    rows = (await db.execute(select(ForumInsightExtracted))).scalars().all()
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r.company_id, r.role_family or "general")].append(
            {
                "post_id": r.post_id,
                "company_id": r.company_id,
                "role_family": r.role_family,
                "school_tier": r.school_tier,
                "degree": r.degree,
                "skills": r.skills or [],
                "soft_skills": r.soft_skills or [],
                "leadership_signals": r.leadership_signals or [],
                "platform": r.platform,
                "weight": r.weight,
                "extraction_confidence": r.extraction_confidence,
                "is_offer_story": bool(r.is_offer_story),
                "post_type": getattr(r, "post_type", None)
                or ("offer" if r.is_offer_story else "discussion"),
                "recruitment_type": getattr(r, "recruitment_type", None) or "unknown",
            }
        )
    return grouped
