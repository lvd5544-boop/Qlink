import re
import os
import copy
import shutil
import logging
logger = logging.getLogger(__name__)


from contextlib import asynccontextmanager
import asyncio
from typing import Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, delete as sql_delete 
from pydantic import BaseModel
import redis.asyncio as aioredis
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .foreign_job_fetcher import fetch_foreign_jobs
from .resume_parser import extract_text_from_pdf, extract_text_from_docx, parse_with_llm
from .models import ResumeInfo, JobInfo
from .database import engine, Base, get_db, AsyncSessionLocal
from .db_schema import ensure_schema
from .models_db import User, Resume, JobDescription, MatchResult, ResumeVariant
from .interview import interview_handler
from .job_parser import parse_job_with_llm
from .matching import generate_matches, generate_matches_auto, generate_matches_for_user
from .resume_health import compute_resume_health
from .resume_suggestions import (
    apply_suggestion_patch,
    build_actionable_suggestions,
    build_coach_actionable_suggestions,
    compute_suggestion_impact,
)
from .resume_suggestion_store import (
    list_pending_suggestions,
    mark_suggestion_by_key,
    mark_suggestion_status,
    sync_suggestions_for_source,
)
from .resume_coach import generate_resume_coach
from .evidence_followup import (
    generate_followup_questions,
    get_entry_context,
    list_unquantified_entries,
    regenerate_evidence_sentence,
)
from .resume_variants import generate_resume_variant, list_style_templates
from .matching_hybrid import full_match_evaluation, extract_breakdown_for_api
from .auth import get_current_user
from .auth_routes import router as auth_router
from .guoqi_job_fetcher import fetch_guoqi_jobs
from .invitation_routes import router as invitation_router
from .application_routes import router as application_router
from .analytics_routes import router as analytics_router
from .market_analytics import run_full_analytics_rebuild
from .job_sources import job_source_label, job_source_type

load_dotenv()

# 全局 Redis 客户端
redis_client = aioredis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True
)

import app.interview as interview_mod
interview_mod.redis_client = redis_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 创建表等原有逻辑...
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_schema(engine)

    async def _startup_analytics():
        try:
            await run_full_analytics_rebuild()
            logger.info("市场洞察与录用画像初始化完成")
        except Exception as e:
            logger.warning("分析数据初始化失败（可稍后手动 /analytics/rebuild）: %s", e)

    # 后台跑分析重建，避免阻塞登录/API（论坛抓取可能很慢）
    asyncio.create_task(_startup_analytics())

    # 启动定时任务（每周一凌晨 2:00）
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        fetch_foreign_jobs,
        trigger="cron",
        day_of_week="mon",
        hour=2,
        minute=0,
        id="weekly_foreign_job_fetch"
    )
    scheduler.add_job(
        fetch_guoqi_jobs,
        trigger="cron",
        day_of_week="mon",
        hour=4,
        minute=0,
        id="weekly_guoqi_job_fetch"
    )
    scheduler.add_job(
        generate_matches_auto,
        kwargs={"llm_rerank_top": 20},
        trigger="cron",
        day_of_week="sun",
        hour=3,
        minute=0,
        id="nightly_llm_match"
    )
    scheduler.add_job(
        run_full_analytics_rebuild,
        trigger="cron",
        day_of_week="sun",
        hour=5,
        minute=0,
        id="weekly_analytics_rebuild"
    )
    from .forum_insight_pipeline import sync_forum_insights_to_db
    from .market_analytics import rebuild_hired_benchmarks_statistical

    async def _weekly_forum_sync():
        async with AsyncSessionLocal() as db:
            await sync_forum_insights_to_db(db)
            await rebuild_hired_benchmarks_statistical(db)

    scheduler.add_job(
        _weekly_forum_sync,
        trigger="cron",
        day_of_week="wed",
        hour=3,
        minute=0,
        id="weekly_forum_insight_sync",
    )
    scheduler.start()
    logger.info("岗位抓取定时任务已启动（外企周一02:00 / 国企周一04:00）")

    yield

    scheduler.shutdown()
    await engine.dispose()
    await redis_client.close()

app = FastAPI(title="AI Job Platform", lifespan=lifespan)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

app.include_router(invitation_router)
app.include_router(application_router)
app.include_router(analytics_router)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 注入 redis 给 interview 模块
import app.interview as interview_mod
interview_mod.redis_client = redis_client

# ------------- 简历体检 ---------------
class ResumeHealthResponse(BaseModel):
    resume_id: str
    health_check: Dict[str, Any]


async def _run_and_save_health_check(db: AsyncSession, resume: Resume) -> dict:
    result = compute_resume_health(resume.parsed_json)
    actionable = build_actionable_suggestions(resume.parsed_json, result)
    result["actionable_suggestions"] = actionable
    resume.health_check = result
    await db.commit()
    pending = await sync_suggestions_for_source(
        db, str(resume.id), "health_check", actionable
    )
    result["pending_suggestions"] = pending
    return result


async def _refresh_resume_matches(
    db: AsyncSession,
    resume_id: str,
    *,
    llm_rerank_top: int = 3,
) -> None:
    await generate_matches(
        db,
        resume_id=resume_id,
        force_refresh=True,
        llm_rerank_top=llm_rerank_top,
    )


@app.post("/resumes/{resume_id}/health-check", response_model=ResumeHealthResponse)
async def resume_health_check(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该简历")

    health = await _run_and_save_health_check(db, resume)
    return {"resume_id": str(resume.id), "health_check": health}


# ------------- 简历解析 ---------------
class ParseResumeResponse(ResumeInfo):
    resume_id: str
    health_check: Optional[Dict[str, Any]] = None


@app.post("/parse-resume", response_model=ParseResumeResponse)
async def parse_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    ext = os.path.splitext(file.filename)[-1].lower()
    try:
        if ext == ".pdf":
            text = extract_text_from_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            text = extract_text_from_docx(file_path)
        elif ext == ".txt":
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        else:
            raise HTTPException(status_code=400, detail="仅支持 PDF, DOCX, TXT 格式")
    finally:
        os.remove(file_path)
    resume_data = parse_with_llm(text)
    if resume_data is None:
        raise HTTPException(status_code=500, detail="AI 解析返回了空结果")
    user = await db.get(User, str(current_user.id))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    resume_record = Resume(
        user_id=str(current_user.id),
        raw_text=text,
        parsed_json=resume_data.model_dump()
    )
    db.add(resume_record)
    await db.commit()
    await db.refresh(resume_record)

    health = await _run_and_save_health_check(db, resume_record)

    asyncio.create_task(_background_match_after_upload(str(resume_record.id)))

    return {
        **resume_data.model_dump(),
        "resume_id": str(resume_record.id),
        "health_check": health,
    }


async def _background_match_after_upload(resume_id: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            await _refresh_resume_matches(db, resume_id, llm_rerank_top=3)
            logger.info("上传后匹配完成 resume_id=%s", resume_id)
    except Exception as e:
        logger.warning("上传后匹配失败 resume_id=%s: %s", resume_id, e)

# ------------- 简历查询 ---------------
@app.get("/resumes/{user_id}")
async def get_user_resumes(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="无权查看他人简历")
    stmt = select(Resume).where(Resume.user_id == user_id).order_by(Resume.uploaded_at.desc())
    result = await db.execute(stmt)
    resumes = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "parsed": r.parsed_json,
            "health_check": r.health_check,
            "raw_text_preview": (r.raw_text or "")[:500] if r.raw_text else None,
            "has_raw_text": bool(r.raw_text),
            "uploaded_at": r.uploaded_at.isoformat()
        }
        for r in resumes
    ]

@app.get("/resume/{resume_id}")
async def get_resume_by_id(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")

    user_id = str(current_user.id)
    if resume.user_id != user_id:
        if current_user.role != "employer":
            raise HTTPException(status_code=403, detail="无权查看该简历")
        match_stmt = select(MatchResult).where(MatchResult.resume_id == resume_id)
        match_result = await db.execute(match_stmt)
        matches = match_result.scalars().all()
        if not matches:
            raise HTTPException(status_code=403, detail="无权查看该简历")
        job_ids = [m.job_id for m in matches]
        job_stmt = select(JobDescription).where(
            JobDescription.id.in_(job_ids),
            JobDescription.employer_id == user_id,
        )
        job_result = await db.execute(job_stmt)
        if not job_result.scalars().first():
            raise HTTPException(status_code=403, detail="无权查看该简历")
    return {
        "id": str(resume.id),
        "user_id": resume.user_id,
        "parsed": resume.parsed_json,
        "health_check": resume.health_check,
        "raw_text": resume.raw_text,
        "uploaded_at": resume.uploaded_at.isoformat()
    }

# ------------- 简历编辑 ---------------
class ResumeUpdate(BaseModel):
    parsed_json: Dict[str, Any]


class ApplySuggestionRequest(BaseModel):
    patch: Dict[str, Any]
    job_id: Optional[str] = None
    suggestion_id: Optional[str] = None
    suggestion_key: Optional[str] = None


class DismissSuggestionRequest(BaseModel):
    suggestion_id: Optional[str] = None
    suggestion_key: Optional[str] = None


class ApplySuggestionResponse(BaseModel):
    status: str
    resume_id: str
    score_delta: float
    old_score: Optional[float] = None
    new_score: Optional[float] = None
    actual_match_score: Optional[float] = None
    health_score_delta: float = 0.0
    health_old_score: Optional[int] = None
    health_new_score: Optional[int] = None
    completeness_delta: float = 0.0
    quantification_delta: float = 0.0
    job_id: Optional[str] = None
    job_title: Optional[str] = None
    health_check: Dict[str, Any]
    parsed_json: Dict[str, Any]
    dashboard_indicators: Optional[Dict[str, Any]] = None


class PreviewSuggestionResponse(BaseModel):
    score_delta: float
    old_score: Optional[float] = None
    new_score: Optional[float] = None
    health_score_delta: float = 0.0
    health_old_score: Optional[int] = None
    health_new_score: Optional[int] = None
    completeness_delta: float = 0.0
    quantification_delta: float = 0.0
    job_id: Optional[str] = None
    job_title: Optional[str] = None


class ResumeCoachRequest(BaseModel):
    company_id: str
    role_family: Optional[str] = None
    target_job_title: Optional[str] = None


class EvidenceFollowupQuestionsRequest(BaseModel):
    entry_type: str  # work | project
    index: int


class EvidenceFollowupAnswer(BaseModel):
    id: Optional[str] = None
    question: Optional[str] = None
    answer: str


class EvidenceFollowupRegenerateRequest(BaseModel):
    entry_type: str
    index: int
    answers: list[EvidenceFollowupAnswer]


class GenerateVariantRequest(BaseModel):
    target_job_title: str
    style_template: str = "balanced"
    job_id: Optional[str] = None


class ApplyVariantRequest(BaseModel):
    variant_id: str


async def _resolve_target_job(
    db: AsyncSession,
    resume_id: str,
    job_id: Optional[str] = None,
) -> Optional[JobDescription]:
    if job_id:
        return await db.get(JobDescription, job_id)
    top = await _get_top_match_for_resume(db, resume_id)
    if top:
        return await db.get(JobDescription, top["job_id"])
    return None


async def _get_match_score_for_job(
    db: AsyncSession,
    resume_id: str,
    job_id: str,
) -> Optional[float]:
    stmt = select(MatchResult).where(
        MatchResult.resume_id == resume_id,
        MatchResult.job_id == job_id,
    )
    match = (await db.execute(stmt)).scalars().first()
    return float(match.score) if match else None


async def _get_top_matches_for_resume(
    db: AsyncSession,
    resume_id: str,
    limit: int = 2,
) -> list[dict]:
    stmt = (
        select(MatchResult)
        .where(MatchResult.resume_id == resume_id)
        .order_by(MatchResult.score.desc())
        .limit(limit)
    )
    matches = (await db.execute(stmt)).scalars().all()
    job_ids = list({m.job_id for m in matches})
    job_map = {}
    if job_ids:
        job_stmt = select(JobDescription).where(JobDescription.id.in_(job_ids))
        for job in (await db.execute(job_stmt)).scalars().all():
            job_map[str(job.id)] = job
    return [
        {
            "job_id": str(m.job_id),
            "job_title": job_map[str(m.job_id)].title if str(m.job_id) in job_map else "未知岗位",
            "score": m.score,
            "potential_score": (m.score_breakdown or {}).get("potential_score"),
        }
        for m in matches
    ]


def _build_dashboard_indicators(
    health_check: Optional[dict],
    top_match_score: Optional[float],
    top_match_title: Optional[str],
) -> dict:
    health = health_check or {}
    return {
        "health_score": health.get("overall_score"),
        "completeness_score": (health.get("completeness") or {}).get("score"),
        "quantification_score": (health.get("quantification") or {}).get("score"),
        "top_match_score": top_match_score,
        "top_match_title": top_match_title,
    }


@app.put("/resumes/{resume_id}")
async def update_resume(
    resume_id: str,
    update: ResumeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权修改该简历")
    cleaned = {k: v for k, v in update.parsed_json.items() if not k.startswith("_")}
    resume.parsed_json = cleaned
    await db.commit()

    health = await _run_and_save_health_check(db, resume)
    await _refresh_resume_matches(db, resume_id, llm_rerank_top=3)

    top_match = await _get_top_match_for_resume(db, resume_id)
    indicators = _build_dashboard_indicators(
        health,
        top_match.get("score") if top_match else None,
        top_match.get("job_title") if top_match else None,
    )
    return {
        "status": "ok",
        "health_check": health,
        "top_match": top_match,
        "dashboard_indicators": indicators,
    }


async def _get_top_match_for_resume(db: AsyncSession, resume_id: str) -> Optional[dict]:
    stmt = (
        select(MatchResult)
        .where(MatchResult.resume_id == resume_id)
        .order_by(MatchResult.score.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    match = result.scalars().first()
    if not match:
        return None
    job = await db.get(JobDescription, match.job_id)
    return {
        "job_id": str(match.job_id),
        "job_title": job.title if job else "未知岗位",
        "score": match.score,
        "potential_score": (match.score_breakdown or {}).get("potential_score"),
    }


@app.post("/resumes/{resume_id}/coach")
async def resume_coach_for_resume(
    resume_id: str,
    body: ResumeCoachRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """内嵌简历诊断（无需跳转 Analytics）。"""
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该简历")

    try:
        result = await generate_resume_coach(
            db,
            resume.parsed_json or {},
            body.company_id,
            body.role_family,
            body.target_job_title,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"简历诊断失败: {e}")

    coach_actionable = build_coach_actionable_suggestions(
        resume.parsed_json or {},
        result,
    )
    pending_coach = await sync_suggestions_for_source(
        db,
        resume_id,
        "coach",
        coach_actionable,
    )
    result["actionable_suggestions"] = coach_actionable
    result["pending_suggestions"] = await list_pending_suggestions(db, resume_id)
    result["coach_suggestions_count"] = len(coach_actionable)
    return result


@app.get("/resumes/{resume_id}/suggestions")
async def get_resume_suggestions(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该简历")

    pending = await list_pending_suggestions(db, resume_id)
    if not pending and resume.health_check:
        actionable = build_actionable_suggestions(
            resume.parsed_json or {},
            resume.health_check,
        )
        if actionable:
            pending = await sync_suggestions_for_source(
                db, resume_id, "health_check", actionable
            )
    return {"resume_id": resume_id, "suggestions": pending}


@app.post("/resumes/{resume_id}/preview-suggestion", response_model=PreviewSuggestionResponse)
async def preview_resume_suggestion(
    resume_id: str,
    body: ApplySuggestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """预览建议采纳后的 score_delta（不写入数据库）。"""
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该简历")

    old_json = copy.deepcopy(resume.parsed_json or {})
    try:
        new_json = apply_suggestion_patch(old_json, body.patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    target_job = await _resolve_target_job(db, resume_id, body.job_id)
    impact = compute_suggestion_impact(
        old_json,
        new_json,
        target_job.parsed_json if target_job else None,
        target_job.title if target_job else "",
    )
    return {
        **impact,
        "job_id": str(target_job.id) if target_job else None,
        "job_title": target_job.title if target_job else None,
    }


@app.post("/resumes/{resume_id}/apply-suggestion", response_model=ApplySuggestionResponse)
async def apply_resume_suggestion(
    resume_id: str,
    body: ApplySuggestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权修改该简历")

    old_json = copy.deepcopy(resume.parsed_json or {})
    try:
        new_json = apply_suggestion_patch(old_json, body.patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    target_job = await _resolve_target_job(db, resume_id, body.job_id)
    impact = compute_suggestion_impact(
        old_json,
        new_json,
        target_job.parsed_json if target_job else None,
        target_job.title if target_job else "",
    )

    resume.parsed_json = new_json
    await db.commit()
    health = await _run_and_save_health_check(db, resume)
    await _refresh_resume_matches(db, resume_id, llm_rerank_top=3)

    if body.suggestion_id:
        await mark_suggestion_status(
            db,
            body.suggestion_id,
            "applied",
            score_delta=impact["score_delta"],
        )
    elif body.suggestion_key:
        await mark_suggestion_by_key(
            db,
            resume_id,
            body.suggestion_key,
            "applied",
            score_delta=impact["score_delta"],
        )

    actual_match_score = None
    job_id = job_title = None
    if target_job:
        job_id = str(target_job.id)
        job_title = target_job.title
        actual_match_score = await _get_match_score_for_job(db, resume_id, job_id)

    top = await _get_top_match_for_resume(db, resume_id)
    indicators = _build_dashboard_indicators(
        health,
        top.get("score") if top else None,
        top.get("job_title") if top else None,
    )

    return {
        "status": "ok",
        "resume_id": resume_id,
        "score_delta": impact["score_delta"],
        "old_score": impact.get("old_score"),
        "new_score": impact.get("new_score"),
        "actual_match_score": actual_match_score,
        "health_score_delta": impact["health_score_delta"],
        "health_old_score": impact["health_old_score"],
        "health_new_score": impact["health_new_score"],
        "completeness_delta": impact["completeness_delta"],
        "quantification_delta": impact["quantification_delta"],
        "job_id": job_id,
        "job_title": job_title,
        "health_check": health,
        "parsed_json": new_json,
        "dashboard_indicators": indicators,
        "pending_suggestions": await list_pending_suggestions(db, resume_id),
    }


@app.post("/resumes/{resume_id}/dismiss-suggestion")
async def dismiss_resume_suggestion(
    resume_id: str,
    body: DismissSuggestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权修改该简历")

    if body.suggestion_id:
        updated = await mark_suggestion_status(db, body.suggestion_id, "dismissed")
        if not updated:
            raise HTTPException(status_code=404, detail="建议不存在")
    elif body.suggestion_key:
        await mark_suggestion_by_key(db, resume_id, body.suggestion_key, "dismissed")
    else:
        raise HTTPException(status_code=400, detail="需提供 suggestion_id 或 suggestion_key")

    return {
        "status": "ok",
        "pending_suggestions": await list_pending_suggestions(db, resume_id),
    }


@app.get("/resumes/{resume_id}/evidence-followup/unquantified")
async def list_unquantified_for_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出缺量化的经历/项目，供前端触发追问弹窗。"""
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该简历")

    entries = list_unquantified_entries(resume.parsed_json or {})
    return {
        "resume_id": resume_id,
        "count": len(entries),
        "entries": [
            {
                "entry_type": e["entry_type"],
                "index": e["index"],
                "name": e["name"],
                "role": e.get("role"),
                "description_preview": (e.get("description") or "")[:120],
            }
            for e in entries
        ],
    }


@app.post("/resumes/{resume_id}/evidence-followup/questions")
async def evidence_followup_questions(
    resume_id: str,
    body: EvidenceFollowupQuestionsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """缺量化时生成 2~3 个追问。"""
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该简历")

    try:
        context = get_entry_context(resume.parsed_json or {}, body.entry_type, body.index)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    questions = generate_followup_questions(context)
    return {
        "resume_id": resume_id,
        "entry_type": body.entry_type,
        "index": body.index,
        "context": {
            "name": context["name"],
            "role": context.get("role"),
            "example_before": context.get("description") or "（暂无描述）",
            "field_path": context["field_path"],
        },
        "questions": questions,
    }


@app.post("/resumes/{resume_id}/evidence-followup/regenerate")
async def evidence_followup_regenerate(
    resume_id: str,
    body: EvidenceFollowupRegenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """用户回答追问后，生成带数字的 example_after 证据句。"""
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该简历")

    if not body.answers:
        raise HTTPException(status_code=400, detail="请至少回答一个问题")

    try:
        context = get_entry_context(resume.parsed_json or {}, body.entry_type, body.index)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = regenerate_evidence_sentence(
        context,
        [a.model_dump() for a in body.answers],
    )
    return {
        "resume_id": resume_id,
        **result,
    }


@app.get("/resume-variant-templates")
async def get_variant_style_templates():
    """5 种岗位定制风格模板。"""
    return {"templates": list_style_templates()}


@app.get("/resumes/{resume_id}/variants")
async def list_resume_variants(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该简历")

    stmt = (
        select(ResumeVariant)
        .where(ResumeVariant.resume_id == resume_id)
        .order_by(ResumeVariant.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "resume_id": resume_id,
        "variants": [
            {
                "id": str(v.id),
                "variant_key": v.variant_key,
                "label": v.label,
                "target_job_title": v.target_job_title,
                "style_template": v.style_template,
                "source": v.source,
                "job_id": v.job_id,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in rows
        ],
    }


@app.post("/resumes/{resume_id}/variants/generate")
async def create_resume_variant(
    resume_id: str,
    body: GenerateVariantRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """生成岗位定制版简历副本，如「Java 后端版」。"""
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该简历")

    job_json = None
    job_title = ""
    if body.job_id:
        job = await db.get(JobDescription, body.job_id)
        if job:
            job_json = job.parsed_json
            job_title = job.title

    generated = await generate_resume_variant(
        resume.parsed_json or {},
        body.target_job_title,
        body.style_template,
        job_json,
        job_title,
    )

    stmt = select(ResumeVariant).where(
        ResumeVariant.resume_id == resume_id,
        ResumeVariant.variant_key == generated["variant_key"],
    )
    existing = (await db.execute(stmt)).scalars().first()
    if existing:
        existing.label = generated["label"]
        existing.target_job_title = generated["target_job_title"]
        existing.style_template = generated["style_template"]
        existing.parsed_json = generated["parsed_json"]
        existing.source = generated["source"]
        existing.job_id = body.job_id
        variant = existing
    else:
        variant = ResumeVariant(
            resume_id=resume_id,
            variant_key=generated["variant_key"],
            label=generated["label"],
            target_job_title=generated["target_job_title"],
            style_template=generated["style_template"],
            parsed_json=generated["parsed_json"],
            source=generated["source"],
            job_id=body.job_id,
        )
        db.add(variant)

    await db.commit()
    await db.refresh(variant)

    return {
        "status": "ok",
        "variant": {
            "id": str(variant.id),
            "variant_key": variant.variant_key,
            "label": variant.label,
            "target_job_title": variant.target_job_title,
            "style_template": variant.style_template,
            "style_label": generated.get("style_label"),
            "parsed_json": variant.parsed_json,
            "source": variant.source,
            "job_id": variant.job_id,
            "created_at": variant.created_at.isoformat() if variant.created_at else None,
        },
    }


@app.get("/resumes/{resume_id}/variants/{variant_id}")
async def get_resume_variant(
    resume_id: str,
    variant_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该简历")

    variant = await db.get(ResumeVariant, variant_id)
    if not variant or variant.resume_id != resume_id:
        raise HTTPException(status_code=404, detail="定制版不存在")

    return {
        "id": str(variant.id),
        "variant_key": variant.variant_key,
        "label": variant.label,
        "target_job_title": variant.target_job_title,
        "style_template": variant.style_template,
        "parsed_json": variant.parsed_json,
        "source": variant.source,
        "job_id": variant.job_id,
        "created_at": variant.created_at.isoformat() if variant.created_at else None,
    }


@app.post("/resumes/{resume_id}/variants/apply")
async def apply_resume_variant(
    resume_id: str,
    body: ApplyVariantRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """将定制版内容写回主简历。"""
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权修改该简历")

    variant = await db.get(ResumeVariant, body.variant_id)
    if not variant or variant.resume_id != resume_id:
        raise HTTPException(status_code=404, detail="定制版不存在")

    resume.parsed_json = copy.deepcopy(variant.parsed_json)
    await db.commit()
    health = await _run_and_save_health_check(db, resume)
    await _refresh_resume_matches(db, resume_id, llm_rerank_top=3)
    top = await _get_top_match_for_resume(db, resume_id)
    indicators = _build_dashboard_indicators(
        health,
        top.get("score") if top else None,
        top.get("job_title") if top else None,
    )
    return {
        "status": "ok",
        "resume_id": resume_id,
        "variant_label": variant.label,
        "parsed_json": resume.parsed_json,
        "health_check": health,
        "dashboard_indicators": indicators,
    }


@app.delete("/resumes/{resume_id}/variants/{variant_id}")
async def delete_resume_variant(
    resume_id: str,
    variant_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权修改该简历")

    variant = await db.get(ResumeVariant, variant_id)
    if not variant or variant.resume_id != resume_id:
        raise HTTPException(status_code=404, detail="定制版不存在")

    await db.delete(variant)
    await db.commit()
    return {"status": "ok"}


@app.get("/dashboard/candidate/{user_id}")
async def candidate_dashboard_summary(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """工作台三指标：体检分、完整度、最高匹配分。"""
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="无权查看他人数据")

    stmt = select(Resume).where(Resume.user_id == user_id).order_by(Resume.uploaded_at.desc())
    resumes = (await db.execute(stmt)).scalars().all()
    latest = resumes[0] if resumes else None

    health = latest.health_check if latest else None
    overall_score = (health or {}).get("overall_score")
    completeness_score = ((health or {}).get("completeness") or {}).get("score")

    top_match_score = None
    top_match_title = None
    top_matches: list[dict] = []
    if latest:
        top_matches = await _get_top_matches_for_resume(db, str(latest.id), limit=2)
        if top_matches:
            top_match_score = top_matches[0].get("score")
            top_match_title = top_matches[0].get("job_title")

    resume_stmt = select(MatchResult).join(Resume, MatchResult.resume_id == Resume.id).where(
        Resume.user_id == user_id
    )
    match_count = len((await db.execute(resume_stmt)).scalars().all())

    indicators = _build_dashboard_indicators(health, top_match_score, top_match_title)

    return {
        "resume_count": len(resumes),
        "match_count": match_count,
        "latest_resume_id": str(latest.id) if latest else None,
        "health_score": overall_score,
        "completeness_score": completeness_score,
        "quantification_score": ((health or {}).get("quantification") or {}).get("score"),
        "top_match_score": top_match_score,
        "top_match_title": top_match_title,
        "top_matches": top_matches,
        "indicators": indicators,
        "health_check": health,
    }

# ------------- 简历删除 ---------------
@app.delete("/resumes/{resume_id}")
async def delete_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权删除该简历")

    # 删除关联的匹配记录（如果有）
    await db.execute(
        sql_delete(MatchResult).where(MatchResult.resume_id == resume_id)
    )
    await db.delete(resume)
    await db.commit()
    return {"status": "ok"}

# ------------- 岗位发布 ---------------
@app.post("/post-job", response_model=JobInfo)
async def post_job(
    employer_id: str = "employer-001",
    file: Optional[UploadFile] = None,
    description_text: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    if file:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        ext = os.path.splitext(file.filename)[-1].lower()
        if ext == ".pdf":
            text = extract_text_from_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            text = extract_text_from_docx(file_path)
        elif ext == ".txt":
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        else:
            os.remove(file_path)
            raise HTTPException(status_code=400, detail="仅支持 PDF, DOCX, TXT 格式")
        os.remove(file_path)
    elif description_text:
        text = description_text
    else:
        raise HTTPException(status_code=400, detail="请上传文件或填写 description_text")
    try:
        job_data = parse_job_with_llm(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 解析失败: {str(e)}")
    emp = await db.get(User, employer_id)
    if not emp:
        emp = User(id=employer_id, email=f"{employer_id}@example.com")
        db.add(emp)
    jd = JobDescription(
        employer_id=employer_id,
        title=job_data.title or "未命名岗位",
        raw_text=text,
        parsed_json=job_data.model_dump()
    )
    db.add(jd)
    await db.commit()
    return job_data

# ------------- 岗位查询 ---------------
@app.get("/jobs/{employer_id}")
async def get_jobs(employer_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(JobDescription).where(JobDescription.employer_id == employer_id).order_by(JobDescription.created_at.desc())
    result = await db.execute(stmt)
    jobs = result.scalars().all()
    return [
        {
            "id": str(j.id),
            "title": j.title,
            "parsed": j.parsed_json,
            "created_at": j.created_at.isoformat()
        }
        for j in jobs
    ]

@app.post("/jobs/sync-sources")
async def sync_job_sources(db: AsyncSession = Depends(get_db)):
    """手动同步国企 + 外企岗位数据源"""
    await fetch_foreign_jobs()
    await fetch_guoqi_jobs()
    await run_full_analytics_rebuild()
    return {
        "msg": "岗位与数据分析已同步",
        "sources": ["国企-国资央企", "外企-Remotive/Arbeitnow", "录用画像-网络论坛统计"],
    }


@app.get("/browse-jobs")
async def browse_jobs(
    keyword: Optional[str] = None,
    location: Optional[str] = None,
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    source_type: Optional[str] = None,
    sort_by: str = "created_at",
    db: AsyncSession = Depends(get_db)
):
    stmt = select(JobDescription)
    if keyword:
        like_pattern = f"%{keyword}%"
        stmt = stmt.where(
            (JobDescription.title.ilike(like_pattern)) |
            (JobDescription.raw_text.ilike(like_pattern))
        )
    result = await db.execute(stmt.order_by(JobDescription.created_at.desc()))
    jobs = result.scalars().all()

    # 地点过滤
    if location:
        jobs = [j for j in jobs if j.parsed_json and
                location in (j.parsed_json.get("location") or "")]
    
    # 薪资范围过滤
    def parse_salary_range(salary_str):
        """解析 '25k-35k' 或 '25000-35000' 返回 (最低, 最高) 单位为k"""
        if not salary_str:
            return None
        nums = re.findall(r'[\d.]+', salary_str)
        if len(nums) >= 2:
            low = float(nums[0])
            high = float(nums[1])
            # 如果数字较大（>1000）认为是元，转换为k
            if low > 1000:
                return (low / 1000, high / 1000)
            return (low, high)
        elif len(nums) == 1:
            num = float(nums[0])
            return (num, num) if num <= 1000 else (num / 1000, num / 1000)
        return None

    if salary_min is not None or salary_max is not None:
        filtered = []
        for job in jobs:
            if not job.parsed_json:
                continue
            parsed = parse_salary_range(job.parsed_json.get("salary_range"))
            if parsed is None:
                continue  # 没有薪资信息的岗位直接忽略
            low, high = parsed
            if salary_min is not None and high < salary_min:
                continue
            if salary_max is not None and low > salary_max:
                continue
            filtered.append(job)
        jobs = filtered

    if source_type in ("soe", "foreign", "employer"):
        jobs = [
            j for j in jobs
            if job_source_type(j.employer_id, j.parsed_json) == source_type
        ]

    if sort_by == "created_at":
        jobs = sorted(jobs, key=lambda j: j.created_at, reverse=True)

    return [
        {
            "id": str(j.id),
            "title": j.title,
            "parsed": j.parsed_json,
            "company_name": (j.parsed_json or {}).get("company_name", ""),
            "contact_person": (j.parsed_json or {}).get("contact_person", ""),
            "contact_info": (j.parsed_json or {}).get("contact_info", ""),
            "created_at": j.created_at.isoformat(),
            "source": job_source_label(j.employer_id, j.parsed_json),
            "source_type": job_source_type(j.employer_id, j.parsed_json),
        }
        for j in jobs
    ]
# ------------- 岗位编辑 ---------------
class JobUpdate(BaseModel):
    parsed_json: Dict[str, Any]

@app.put("/jobs/{job_id}")
async def update_job(job_id: str, update: JobUpdate, db: AsyncSession = Depends(get_db)):
    job = await db.get(JobDescription, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")
    job.parsed_json = update.parsed_json
    await db.commit()
    return {"status": "ok"}

@app.get("/job/{job_id}")
async def get_job_detail(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(JobDescription, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return {
        "id": str(job.id),
        "title": job.title,
        "parsed": job.parsed_json,
        "company_name": job.parsed_json.get("company_name", "") if job.parsed_json else "",
        "contact_person": job.parsed_json.get("contact_person", "") if job.parsed_json else "",
        "contact_info": job.parsed_json.get("contact_info", "") if job.parsed_json else "",
        "created_at": job.created_at.isoformat()
    }

# ------------- 岗位删除 ---------------
@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str, db: AsyncSession = Depends(get_db)):
    # 检查岗位是否存在
    job = await db.get(JobDescription, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")

    try:
        # 1. 先删除该岗位下的所有匹配记录（使用批量删除）
        await db.execute(
            sql_delete(MatchResult).where(MatchResult.job_id == job_id)
        )
        # 2. 删除岗位本身
        await db.delete(job)
        await db.commit()
        return {"status": "ok"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")

# ------------- 匹配 ---------------
class MatchEvaluateRequest(BaseModel):
    resume_id: Optional[str] = None
    job_id: Optional[str] = None

@app.post("/match/evaluate")
async def evaluate_match(
    req: MatchEvaluateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """v2 完整匹配评估：十维 breakdown + 补充信号 + 职业建议。"""
    if not req.resume_id or not req.job_id:
        raise HTTPException(status_code=400, detail="需要 resume_id 和 job_id")

    resume = await db.get(Resume, req.resume_id)
    if not resume or resume.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="简历不存在或无权访问")

    job = await db.get(JobDescription, req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")

    result = full_match_evaluation(
        resume.parsed_json or {},
        job.parsed_json or {},
        job_title=job.title,
    )
    result["resume_id"] = str(resume.id)
    result["job_id"] = str(job.id)
    result["job_title"] = job.title
    return result

@app.post("/match")
async def trigger_matching(
    resume_id: Optional[str] = None,
    job_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    await generate_matches(db, resume_id, job_id)
    return {"status": "ok"}

@app.post("/match/user/{user_id}")
async def match_for_user(
    user_id: str,
    use_llm: bool = True,
    db: AsyncSession = Depends(get_db),
):
    n = await generate_matches_for_user(
        db,
        user_id,
        force_refresh=True,
        llm_rerank_top=5 if use_llm else 0,
    )
    return {"status": "ok", "resumes_processed": n}

@app.get("/matches/user/{user_id}")
async def get_matches_for_user(
    user_id: str,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db)
):
    # 如果需要刷新，先生成匹配（快速本地算法）
    if refresh:
        await generate_matches_for_user(
            db,
            user_id,
            force_refresh=True,
            llm_rerank_top=5,
        )

    # 重新获取简历列表
    resume_stmt = select(Resume).where(Resume.user_id == user_id)
    resume_result = await db.execute(resume_stmt)
    resumes = resume_result.scalars().all()
    if not resumes:
        return []

    resume_ids = [r.id for r in resumes]
    stmt = (
        select(MatchResult)
        .where(MatchResult.resume_id.in_(resume_ids))
        .order_by(MatchResult.score.desc())
        .limit(100)   # 最多 100 个
    )
    result = await db.execute(stmt)
    matches = result.scalars().all()

    # 获取关联岗位信息...（与之前相同）
    job_ids = list({m.job_id for m in matches})
    job_map = {}
    if job_ids:
        job_stmt = select(JobDescription).where(JobDescription.id.in_(job_ids))
        job_result = await db.execute(job_stmt)
        for job in job_result.scalars().all():
            job_map[str(job.id)] = job

    def _serialize_user_match(m: MatchResult) -> dict:
        bd = m.score_breakdown or {}
        breakdown = extract_breakdown_for_api(bd)
        return {
            "id": str(m.id),
            "resume_id": str(m.resume_id),
            "job_id": str(m.job_id),
            "score": m.score,
            "reason": m.reason,
            "score_breakdown": m.score_breakdown,
            "breakdown": breakdown,
            "missing_skills": (breakdown or {}).get("missing_skills") or [],
            "potential_score": bd.get("potential_score"),
            "match_tier": bd.get("match_tier"),
            "improvement_delta": bd.get("improvement_delta"),
            "llm_reranked": bool((bd.get("llm_rerank") or {}).get("source") == "llm_rerank"),
            "job_title": job_map[str(m.job_id)].title if str(m.job_id) in job_map else "未知岗位",
            "job_location": job_map[str(m.job_id)].parsed_json.get("location") if str(m.job_id) in job_map else None,
            "job_salary": job_map[str(m.job_id)].parsed_json.get("salary_range") if str(m.job_id) in job_map else None,
            "created_at": m.created_at.isoformat(),
        }

    return [_serialize_user_match(m) for m in matches]

@app.get("/matches/resume/{resume_id}")
async def get_matches_for_resume(resume_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(MatchResult).where(MatchResult.resume_id == resume_id).order_by(MatchResult.score.desc())
    result = await db.execute(stmt)
    matches = result.scalars().all()

    job_ids = list({m.job_id for m in matches})
    job_map = {}
    if job_ids:
        job_stmt = select(JobDescription).where(JobDescription.id.in_(job_ids))
        job_result = await db.execute(job_stmt)
        for job in job_result.scalars().all():
            job_map[str(job.id)] = job

    return [
        {
            "id": str(m.id),
            "job_id": str(m.job_id),
            "job_title": job_map[str(m.job_id)].title if str(m.job_id) in job_map else "未知岗位",
            "score": m.score,
            "reason": m.reason,
            "score_breakdown": m.score_breakdown,
            "potential_score": (m.score_breakdown or {}).get("potential_score"),
            "created_at": m.created_at.isoformat()
        }
        for m in matches
    ]

@app.get("/matches/job/{job_id}")
async def get_matches_for_job(job_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(MatchResult).where(MatchResult.job_id == job_id).order_by(MatchResult.score.desc())
    result = await db.execute(stmt)
    matches = result.scalars().all()

    resume_ids = list({m.resume_id for m in matches})
    resume_map = {}
    if resume_ids:
        resume_stmt = select(Resume).where(Resume.id.in_(resume_ids))
        resume_result = await db.execute(resume_stmt)
        for r in resume_result.scalars().all():
            resume_map[str(r.id)] = r

    return [
        {
            "id": str(m.id),
            "resume_id": str(m.resume_id),
            "score": m.score,
            "reason": m.reason,
            "score_breakdown": m.score_breakdown,
            "candidate_name": (resume_map[str(m.resume_id)].parsed_json.get("name") if str(m.resume_id) in resume_map else None) or "匿名",
            "expected_title": (resume_map[str(m.resume_id)].parsed_json.get("expected_job_title") if str(m.resume_id) in resume_map else None) or "未填写",
            "created_at": m.created_at.isoformat()
        }
        for m in matches
    ]

# ------------- 虚拟面试官 ---------------
@app.websocket("/ws/interview/{user_id}")
async def websocket_interview(websocket: WebSocket, user_id: str):
    async with AsyncSessionLocal() as db:
        await interview_handler(websocket, user_id, db)

# ------------- 健康检查 ---------------
@app.get("/health")
async def health():
    return {"status": "ok"}
