"""外企 / 国际岗位抓取（Remotive、Arbeitnow 等公开 API）"""

import logging
import re
import httpx
from sqlalchemy import delete

from .database import AsyncSessionLocal
from .models_db import JobDescription, User

logger = logging.getLogger(__name__)

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"

EMPLOYER_ID = "foreign"


def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", "", raw_html)
    return re.sub(r"\s+", " ", clean).strip()


def _normalize_job(
    title: str,
    company_name: str,
    description: str,
    location: str,
    tags: list,
    source_label: str,
    url: str = "",
) -> dict:
    tag_skills = [{"name": t, "level": "intermediate"} for t in (tags or [])[:10] if t]
    return {
        "title": title or "未知岗位",
        "company_name": company_name or "未知企业",
        "company_type": "foreign",
        "salary_range": "",
        "location": location or "远程/海外",
        "required_skills": tag_skills,
        "responsibilities": [description] if description else [],
        "experience_years": None,
        "education": "",
        "other_notes": f"来源: {source_label} | {url}".strip(),
    }


async def _ensure_foreign_employer(db):
    emp = await db.get(User, EMPLOYER_ID)
    if not emp:
        emp = User(id=EMPLOYER_ID, email="foreign@example.com", role="employer")
        db.add(emp)
        await db.flush()
    return emp


async def fetch_remotive_jobs(client: httpx.AsyncClient) -> list:
    jobs = []
    try:
        resp = await client.get(REMOTIVE_URL, timeout=30.0)
        resp.raise_for_status()
        for job in resp.json().get("jobs", []):
            desc = clean_html(job.get("description", ""))
            jobs.append(
                _normalize_job(
                    title=job.get("title", ""),
                    company_name=job.get("company_name", ""),
                    description=desc,
                    location=job.get("candidate_required_location") or "远程",
                    tags=job.get("tags") or [],
                    source_label="Remotive",
                    url=job.get("url", ""),
                )
            )
    except Exception as e:
        logger.error("Remotive 抓取失败: %s", e)
    return jobs


async def fetch_arbeitnow_jobs(client: httpx.AsyncClient) -> list:
    jobs = []
    try:
        resp = await client.get(ARBEITNOW_URL, timeout=30.0)
        resp.raise_for_status()
        for job in resp.json().get("data", []):
            tags = job.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            desc = job.get("description", "") or ""
            jobs.append(
                _normalize_job(
                    title=job.get("title", ""),
                    company_name=job.get("company_name", ""),
                    description=clean_html(desc) if "<" in desc else desc,
                    location=job.get("location", "") or "海外",
                    tags=tags,
                    source_label="Arbeitnow",
                    url=job.get("url", ""),
                )
            )
    except Exception as e:
        logger.error("Arbeitnow 抓取失败: %s", e)
    return jobs


async def fetch_foreign_jobs():
    """抓取外企/国际岗位并入库"""
    logger.info("开始抓取外企/国际岗位...")
    all_parsed = []
    async with httpx.AsyncClient() as client:
        all_parsed.extend(await fetch_remotive_jobs(client))
        all_parsed.extend(await fetch_arbeitnow_jobs(client))

    if not all_parsed:
        logger.info("未获取到外企岗位")
        return

    seen = set()
    unique = []
    for j in all_parsed:
        key = (j["company_name"].lower(), j["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(j)

    async with AsyncSessionLocal() as db:
        await _ensure_foreign_employer(db)
        await db.execute(delete(JobDescription).where(JobDescription.employer_id == EMPLOYER_ID))
        count = 0
        for job_info in unique:
            try:
                jd = JobDescription(
                    employer_id=EMPLOYER_ID,
                    title=job_info["title"],
                    raw_text=job_info["responsibilities"][0]
                    if job_info["responsibilities"]
                    else "",
                    parsed_json=job_info,
                )
                db.add(jd)
                count += 1
            except Exception as e:
                logger.error("处理外企岗位出错: %s", e)
        await db.commit()
        logger.info("成功导入 %s 个外企/国际岗位", count)
