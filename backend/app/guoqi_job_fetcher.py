import logging
import httpx
import re
from datetime import datetime, timezone
from sqlalchemy import select
from .database import AsyncSessionLocal
from .models_db import JobDescription, User

logger = logging.getLogger(__name__)

API_URL = "https://gp-api.iguopin.com/api/jobs/v1/list"

HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Accept": "application/json, text/plain, */*",
    "Device": "pc",
    "Subsite": "cujiuye",
    "Version": "5.0.0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def clean_html(raw_html):
    """去除 HTML 标签"""
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", "", raw_html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


async def fetch_guoqi_jobs(keywords: list = None):
    """从国资央企招聘平台获取岗位信息"""
    if keywords is None:
        keywords = [
            "计算机",
            "信息技术",
            "软件",
            "网络安全",
            "人工智能",
            "大数据",
            "金融",
            "财务",
            "会计",
            "审计",
            "法务",
            "人力资源",
            "市场营销",
            "机械",
            "电气",
            "土木",
            "工程",
            "管理培训生",
            "英语",
            "研发",
            "通信",
            "电子",
            "化工",
            "能源",
            "建筑",
        ]

    all_jobs = []
    async with httpx.AsyncClient() as client:
        for keyword in keywords:
            try:
                for page in range(1, 3):  # 每个关键词最多取2页
                    data = {
                        "page": page,
                        "page_size": 100,
                        "keyword": keyword,
                        "nature": ["115xW5oQ"],
                    }
                    resp = await client.post(API_URL, json=data, headers=HEADERS, timeout=30.0)
                    resp.raise_for_status()
                    res_json = resp.json()
                    jobs_list = res_json.get("data", {}).get("list", [])
                    if not jobs_list:
                        break
                    all_jobs.extend(jobs_list)
                    logger.info(f"关键词 '{keyword}' 第{page}页：获取 {len(jobs_list)} 条")
            except Exception as e:
                logger.error(f"抓取关键词 '{keyword}' 失败: {e}")
                continue

    if not all_jobs:
        logger.info("未获取到国资央企招聘数据")
        return

    # 去重（按 job_id）
    seen = set()
    unique_jobs = []
    for job in all_jobs:
        job_id = job.get("job_id")
        if job_id and job_id not in seen:
            seen.add(job_id)
            unique_jobs.append(job)

    async with AsyncSessionLocal() as db:
        system_employer = await db.get(User, "guoqi")
        if not system_employer:
            system_employer = User(id="guoqi", email="guoqi@example.com", role="employer")
            db.add(system_employer)
            await db.flush()

        existing = (
            (await db.execute(select(JobDescription).where(JobDescription.employer_id == "guoqi")))
            .scalars()
            .all()
        )
        by_source_id = {
            str((row.parsed_json or {}).get("source_job_id")): row
            for row in existing
            if (row.parsed_json or {}).get("source_job_id")
        }
        by_identity = {
            (
                str((row.parsed_json or {}).get("company_name") or "").casefold(),
                str(row.title or "").casefold(),
            ): row
            for row in existing
        }

        count = 0
        for job in unique_jobs:
            try:
                title = job.get("job_name", "未知岗位")
                company_name = job.get("company_name", "")
                area = (
                    job.get("district_list", [{}])[0].get("area_cn", "")
                    if job.get("district_list")
                    else ""
                )
                salary = (
                    f"{job.get('min_wage', '')}-{job.get('max_wage', '')}"
                    if job.get("min_wage")
                    else ""
                )
                education = job.get("education_cn", "")
                nature_cn = (
                    job.get("company_info", {}).get("nature_cn", "")
                    if job.get("company_info")
                    else ""
                )
                contents = clean_html(job.get("contents", ""))
                contents_text = clean_html(job.get("contents", ""))
                contact_person = ""
                contact_info = ""
                # 简单正则提取（可根据实际数据优化）
                phone_match = re.search(r"联系电话[：:]\s*(\S+)", contents_text)
                if phone_match:
                    contact_info = phone_match.group(1)
                email_match = re.search(r"电子邮箱[：:]\s*(\S+@\S+)", contents_text)
                if email_match:
                    if contact_info:
                        contact_info += f" / {email_match.group(1)}"
                    else:
                        contact_info = email_match.group(1)
                person_match = re.search(r"联系人[：:]\s*(\S+)", contents_text)
                if person_match:
                    contact_person = person_match.group(1)

                job_info = {
                    "title": title,
                    "salary_range": salary,
                    "location": area or "全国",
                    "required_skills": [],
                    "responsibilities": [contents_text],
                    "experience_years": None,
                    "education": education,
                    "company_name": company_name,
                    "company_type": "soe",
                    "source_name": "国资央企招聘平台",
                    "source_job_id": str(job.get("job_id") or ""),
                    "source_attribution": "岗位来源：国资央企招聘平台；请以发布方最新页面为准。",
                    "last_seen_at": datetime.now(timezone.utc).isoformat(),
                    "contact_person": contact_person,
                    "contact_info": contact_info,
                    "other_notes": f"来源：国资央企招聘平台 | 公司：{company_name} | 性质：{nature_cn}",
                }

                identity = (company_name.casefold(), title.casefold())
                row = by_source_id.get(job_info["source_job_id"]) or by_identity.get(identity)
                if row is None:
                    row = JobDescription(
                        employer_id="guoqi",
                        title=job_info["title"],
                        raw_text=contents,
                        parsed_json=job_info,
                    )
                    db.add(row)
                else:
                    row.title = job_info["title"]
                    row.raw_text = contents
                    row.parsed_json = job_info
                count += 1
            except Exception as e:
                logger.error(f"处理岗位时出错: {e}")
                continue

        await db.commit()
        logger.info("成功新增或更新 %s 条国资央企岗位；未删除历史岗位", count)
