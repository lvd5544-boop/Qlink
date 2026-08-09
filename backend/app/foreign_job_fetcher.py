"""外企 / 国际岗位聚合。

Each source is fetched independently. A failed source never erases previously
usable jobs, and existing employer-posted jobs are never touched.
"""

import logging
import os
import re
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from .database import AsyncSessionLocal
from .models_db import JobDescription, User
from .text_quality import repair_mojibake, repair_text_tree

logger = logging.getLogger(__name__)

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
REMOTEOK_URL = "https://remoteok.com/api"
USAJOBS_URL = "https://data.usajobs.gov/api/search"
GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
DEFAULT_GREENHOUSE_BOARDS = "anthropic:Anthropic,stripe:Stripe,discord:Discord"

EMPLOYER_ID = "foreign"


def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", "", repair_mojibake(raw_html))
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
    return repair_text_tree(
        {
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
            "source_name": source_label,
            "source_url": url,
            "source_attribution": f"岗位来源：{source_label}；申请时跳转原始岗位页面。",
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        }
    )


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


async def fetch_remoteok_jobs(client: httpx.AsyncClient) -> list:
    jobs = []
    try:
        resp = await client.get(
            REMOTEOK_URL,
            timeout=30.0,
            headers={"User-Agent": "AI Job Platform job aggregation/1.0"},
        )
        resp.raise_for_status()
        payload = resp.json()
        for job in payload if isinstance(payload, list) else []:
            if not isinstance(job, dict) or not job.get("position"):
                continue
            tags = job.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            jobs.append(
                _normalize_job(
                    title=job.get("position", ""),
                    company_name=job.get("company", ""),
                    description=clean_html(job.get("description", "")),
                    location=job.get("location") or "远程",
                    tags=tags,
                    source_label="Remote OK",
                    url=job.get("url") or job.get("apply_url") or "",
                )
            )
    except Exception as exc:
        logger.error("Remote OK 抓取失败: %s", exc)
    return jobs


async def fetch_usajobs_jobs(client: httpx.AsyncClient) -> list:
    """Fetch current public US federal jobs when a free USAJOBS API key is configured."""

    api_key = (os.getenv("USAJOBS_API_KEY") or "").strip()
    user_agent = (os.getenv("USAJOBS_USER_AGENT") or "").strip()
    if not api_key or not user_agent:
        logger.info("USAJOBS 未配置 API Key/User-Agent，跳过当前岗位同步")
        return []
    jobs = []
    try:
        response = await client.get(
            USAJOBS_URL,
            params={
                "Keyword": "software data product engineering",
                "WhoMayApply": "Public",
                "ResultsPerPage": 100,
                "Fields": "Full",
            },
            headers={
                "Host": "data.usajobs.gov",
                "User-Agent": user_agent,
                "Authorization-Key": api_key,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        items = response.json().get("SearchResult", {}).get("SearchResultItems", [])
        for item in items:
            descriptor = item.get("MatchedObjectDescriptor") or {}
            details = (descriptor.get("UserArea") or {}).get("Details") or {}
            locations = descriptor.get("PositionLocation") or []
            location = descriptor.get("PositionLocationDisplay") or ", ".join(
                value.get("LocationName", "") for value in locations[:3]
            )
            description = "\n".join(
                str(details.get(key) or "")
                for key in ("JobSummary", "MajorDuties", "Requirements", "Education")
            ).strip()
            categories = [
                value.get("Name")
                for value in (descriptor.get("JobCategory") or [])
                if value.get("Name")
            ]
            jobs.append(
                _normalize_job(
                    title=descriptor.get("PositionTitle", ""),
                    company_name=descriptor.get("OrganizationName")
                    or descriptor.get("DepartmentName", ""),
                    description=clean_html(description),
                    location=location,
                    tags=categories,
                    source_label="USAJOBS",
                    url=descriptor.get("PositionURI", ""),
                )
            )
    except Exception as exc:
        logger.error("USAJOBS 抓取失败: %s", exc)
    return jobs


def _configured_greenhouse_boards() -> list[tuple[str, str]]:
    raw = (os.getenv("GREENHOUSE_BOARDS") or DEFAULT_GREENHOUSE_BOARDS).strip()
    boards: list[tuple[str, str]] = []
    for value in raw.split(","):
        token, _, label = value.strip().partition(":")
        token = re.sub(r"[^a-zA-Z0-9_-]", "", token)
        if token:
            boards.append((token, label.strip() or token))
    return boards[:20]


async def fetch_greenhouse_jobs(client: httpx.AsyncClient) -> list:
    """Fetch published company jobs through Greenhouse's public GET API."""
    jobs = []
    max_per_board = max(1, min(int(os.getenv("GREENHOUSE_MAX_JOBS_PER_BOARD") or 200), 500))
    for token, company in _configured_greenhouse_boards():
        try:
            response = await client.get(
                GREENHOUSE_URL.format(token=token),
                params={"content": "true"},
                timeout=45.0,
                headers={"User-Agent": "QLink career search/1.0"},
            )
            response.raise_for_status()
            for item in (response.json().get("jobs") or [])[:max_per_board]:
                departments = [
                    str(value.get("name") or "").strip()
                    for value in (item.get("departments") or [])
                    if value.get("name")
                ]
                offices = [
                    str(value.get("location") or value.get("name") or "").strip()
                    for value in (item.get("offices") or [])
                    if value.get("location") or value.get("name")
                ]
                location = str((item.get("location") or {}).get("name") or "").strip()
                jobs.append(
                    _normalize_job(
                        title=item.get("title", ""),
                        company_name=company,
                        description=clean_html(item.get("content", "")),
                        location=location or ", ".join(offices[:2]) or "地点见原岗位",
                        tags=departments,
                        source_label=f"Greenhouse · {company}",
                        url=item.get("absolute_url", ""),
                    )
                )
        except Exception as exc:
            logger.error("Greenhouse 招聘板 %s 抓取失败: %s", token, exc)
    return jobs


async def fetch_foreign_jobs():
    """抓取外企/国际岗位并入库"""
    logger.info("开始抓取外企/国际岗位...")
    all_parsed = []
    async with httpx.AsyncClient() as client:
        all_parsed.extend(await fetch_remotive_jobs(client))
        all_parsed.extend(await fetch_arbeitnow_jobs(client))
        all_parsed.extend(await fetch_remoteok_jobs(client))
        all_parsed.extend(await fetch_usajobs_jobs(client))
        all_parsed.extend(await fetch_greenhouse_jobs(client))

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
        existing = (
            (
                await db.execute(
                    select(JobDescription).where(JobDescription.employer_id == EMPLOYER_ID)
                )
            )
            .scalars()
            .all()
        )
        by_source_url = {
            str((row.parsed_json or {}).get("source_url")): row
            for row in existing
            if (row.parsed_json or {}).get("source_url")
        }
        by_identity = {
            (
                str((row.parsed_json or {}).get("company_name") or "").lower(),
                str(row.title or "").lower(),
            ): row
            for row in existing
        }
        count = 0
        for job_info in unique:
            try:
                row = by_source_url.get(job_info.get("source_url")) or by_identity.get(
                    (job_info["company_name"].lower(), job_info["title"].lower())
                )
                raw_text = job_info["responsibilities"][0] if job_info["responsibilities"] else ""
                if row is None:
                    row = JobDescription(
                        employer_id=EMPLOYER_ID,
                        title=job_info["title"],
                        raw_text=raw_text,
                        parsed_json=job_info,
                    )
                    db.add(row)
                else:
                    row.title = job_info["title"]
                    row.raw_text = raw_text
                    row.parsed_json = job_info
                count += 1
            except Exception as e:
                logger.error("处理外企岗位出错: %s", e)
        await db.commit()
        logger.info("成功新增或更新 %s 个外企/国际岗位；历史岗位未因单源失败被删除", count)
