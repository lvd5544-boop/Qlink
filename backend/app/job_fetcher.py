import os
import re
import logging
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from .database import AsyncSessionLocal
from .models_db import JobDescription, User
from sqlalchemy import select, delete

logger = logging.getLogger(__name__)

REMOTE_API_URL = "https://remotive.com/api/remote-jobs"

def clean_html(raw_html: str) -> str:
    """去除 HTML 标签，只保留纯文本"""
    clean = re.sub(r'<[^>]+>', '', raw_html)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

async def fetch_and_store_jobs():
    logger.info("开始抓取远程岗位...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(REMOTE_API_URL, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            jobs_list = data.get("jobs", [])
    except Exception as e:
        logger.error(f"抓取远程岗位失败: {e}")
        return

    if not jobs_list:
        logger.info("未获取到岗位")
        return

    async with AsyncSessionLocal() as db:
        system_employer = await db.get(User, "system")
        if not system_employer:
            system_employer = User(id="system", email="system@example.com", role="employer")
            db.add(system_employer)
            await db.flush()

        # 清除旧的系统岗位
        await db.execute(
            delete(JobDescription).where(JobDescription.employer_id == "system")
        )

        count = 0
        for job in jobs_list:
            try:
                description_raw = job.get("description", "")
                clean_desc = clean_html(description_raw)  # 去除 HTML，保留全文
                job_info = {
                    "title": job.get("title", "未知岗位"),
                    "salary_range": job.get("salary", ""),
                    "location": "远程",
                    "required_skills": [{"name": tag, "level": "intermediate"} for tag in job.get("tags", [])[:8]],
                    "responsibilities": [clean_desc],   # 完整干净文本
                    "experience_years": None,
                    "education": "",
                    "other_notes": f"来源: {job.get('url', '')}"
                }

                jd = JobDescription(
                    employer_id="system",
                    title=job_info["title"],
                    raw_text=description_raw,
                    parsed_json=job_info
                )
                db.add(jd)
                count += 1
            except Exception as e:
                logger.error(f"处理岗位时出错: {e}")
                continue

        await db.commit()
        logger.info(f"成功导入 {count} 个远程岗位")