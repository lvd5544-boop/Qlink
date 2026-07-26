import re
import os
import copy
import logging
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, WebSocket, Header
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import redis.asyncio as aioredis
from dotenv import load_dotenv
from .resume_parser import extract_text_from_pdf, extract_text_from_docx, parse_with_llm
from .models import ResumeInfo, JobInfo
from .database import engine, get_db, AsyncSessionLocal
from .models_db import (
    JobApplication,
    User,
    Resume,
    JobDescription,
    MatchResult,
    ResumeVariant,
)
from .interview import interview_handler, claim_followup_handler
from .interview_fair_use import (
    close_interview_session,
    send_fair_use_error,
    start_interview_session,
)
from .job_parser import parse_job_with_llm
from .resume_health import compute_resume_health
from .resume_suggestions import (
    apply_suggestion_patch,
    build_actionable_suggestions,
    compute_suggestion_impact,
    validate_client_patch_against_stored,
)
from .resume_suggestion_store import (
    get_suggestion_by_id,
    get_suggestion_by_key,
    list_pending_suggestions,
    mark_suggestion_by_key,
    mark_suggestion_status,
    sync_suggestions_for_source,
)
from .resume_coach_service import run_resume_coach
from .claim_reasoning import generate_claim_followup_pack, reason_about_claims
from .evidence_followup import (
    analyze_followup_answers,
    generate_followup_questions,
    get_entry_context,
    list_unquantified_entries,
    match_claim_followup_answers,
    match_clarification_answers,
    regenerate_evidence_sentence,
)
from .resume_variants import generate_resume_variant, list_style_templates
from .matching_hybrid import full_match_evaluation, extract_breakdown_for_api
from .auth import get_current_user, validate_auth_configuration
from .auth_routes import router as auth_router
from .invitation_routes import router as invitation_router
from .application_routes import router as application_router
from .analytics_routes import router as analytics_router
from .billing_routes import router as billing_router
from .interview_routes import router as interview_router
from .billing_accounts import reserve_feature_entitlement
from .job_sources import job_source_label, job_source_type
from .usage_metering import (
    finalize_quota,
    get_usage_summary,
)
from .privacy import delete_job_graph, delete_resume_graph
from .safe_upload import call_parser_bounded, extract_text_bounded, save_upload_safely
from .security import (
    owned_job_or_404,
    owned_resume_or_404,
    require_admin,
    require_candidate,
    require_employer,
)
from .application_authz import application_has_candidate_authorization
from .application_events import event_bus
from .websocket_auth import authenticate_websocket
from .fidelity_proof import (
    create_fidelity_proof,
    validate_fidelity_proof_configuration,
    verify_fidelity_proof,
)
from .provider_costs import (
    record_provider_cost_event,
)
from .api_errors import (
    attach_request_context,
    http_exception_handler,
    validation_exception_handler,
)
from .readiness import collect_readiness, model_runtime_mode
from .schema_version import require_current_schema
from .background_jobs import bind_redis, enqueue_job, enqueue_resume_match, get_job_status
from .llm_client import run_in_thread

load_dotenv()

validate_auth_configuration()
validate_fidelity_proof_configuration()

# 全局 Redis 客户端（面试可选依赖）
try:
    redis_client = aioredis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )
except Exception as _redis_err:
    logger.warning("Redis 初始化失败，面试将使用内存会话: %s", _redis_err)
    redis_client = None

bind_redis(redis_client)

import app.interview as interview_mod

interview_mod.redis_client = redis_client


def _is_testing() -> bool:
    return os.getenv("TESTING", "").strip().lower() in {"1", "true", "yes"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema changes belong exclusively to ``python -m scripts.migrate``.
    # Workers only validate migration state and can therefore scale safely.
    if not _is_testing():
        await require_current_schema(engine)
    event_bus.configure(redis_client)
    try:
        yield
    finally:
        await engine.dispose()
        if redis_client is not None:
            await redis_client.aclose()


app = FastAPI(
    title="AI Job Platform",
    lifespan=lifespan,
    root_path=os.getenv("API_ROOT_PATH", ""),
)
app.middleware("http")(attach_request_context)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


def resolve_cors_origins() -> list[str]:
    environment = os.getenv("ENV", "development").strip().lower()
    configured = os.getenv("CORS_ORIGINS", "").strip()
    if environment == "production":
        origins = [item.strip() for item in configured.split(",") if item.strip()]
        if not origins or "*" in origins:
            raise RuntimeError("生产环境必须配置明确的 CORS_ORIGINS 白名单")
        return origins
    return [item.strip() for item in (configured or "*").split(",") if item.strip()]


_cors_origins = resolve_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials="*" not in _cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

app.include_router(invitation_router)
app.include_router(application_router)
app.include_router(analytics_router)
app.include_router(billing_router)
app.include_router(interview_router)

UPLOAD_DIR = os.getenv("UPLOAD_DIR") or (
    "/data/uploads"
    if os.getenv("ENV", "development").strip().lower() == "production"
    else "uploads"
)
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
    pending = await sync_suggestions_for_source(db, str(resume.id), "health_check", actionable)
    result["pending_suggestions"] = pending
    return result


async def _refresh_resume_matches(
    db: AsyncSession,
    resume_id: str,
    *,
    llm_rerank_top: int = 3,
) -> dict:
    """Queue match refresh off the web worker; tests run inline via TESTING."""
    return await enqueue_job(
        redis_client,
        job_type="match_generate",
        payload={
            "resume_id": str(resume_id),
            "force_refresh": True,
            "llm_rerank_top": llm_rerank_top,
        },
        idempotency_key=f"match_generate:resume:{resume_id}:{llm_rerank_top}",
    )


@app.get("/background-jobs/{job_id}")
async def background_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    status = await get_job_status(redis_client, job_id)
    if not status:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return status


@app.post("/resumes/{resume_id}/health-check", response_model=ResumeHealthResponse)
async def resume_health_check(
    resume_id: str,
    current_user: User = Depends(require_candidate),
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
    match_job_id: Optional[str] = None


@app.post("/parse-resume", response_model=ParseResumeResponse)
async def parse_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    file_path = None
    try:
        file_path, ext = await save_upload_safely(file, UPLOAD_DIR)
        text = await extract_text_bounded(
            file_path,
            ext,
            extract_text_from_pdf,
            extract_text_from_docx,
        )
    finally:
        if file_path is not None:
            file_path.unlink(missing_ok=True)
    resume_data = await call_parser_bounded(parse_with_llm, text)
    if resume_data is None:
        raise HTTPException(status_code=500, detail="AI 解析返回了空结果")
    user = await db.get(User, str(current_user.id))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    resume_record = Resume(
        user_id=str(current_user.id), raw_text=text, parsed_json=resume_data.model_dump()
    )
    db.add(resume_record)
    await db.commit()
    await db.refresh(resume_record)

    health = await _run_and_save_health_check(db, resume_record)

    match_job_id = None
    if not _is_testing():
        try:
            match_job_id = await enqueue_resume_match(
                redis_client,
                str(resume_record.id),
            )
        except Exception as exc:
            logger.error(
                "上传后匹配任务入队失败 resume_id=%s error=%s",
                resume_record.id,
                type(exc).__name__,
            )

    return {
        **resume_data.model_dump(),
        "resume_id": str(resume_record.id),
        "health_check": health,
        "match_job_id": match_job_id,
    }


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
            "uploaded_at": r.uploaded_at.isoformat(),
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
        application_stmt = (
            select(JobApplication)
            .join(JobDescription, JobApplication.job_id == JobDescription.id)
            .where(
                JobApplication.resume_id == resume_id,
                JobApplication.employer_id == user_id,
                JobDescription.employer_id == user_id,
            )
            .order_by(JobApplication.created_at.desc())
        )
        applications = (await db.execute(application_stmt)).scalars().all()
        if not any(application_has_candidate_authorization(app) for app in applications):
            raise HTTPException(status_code=404, detail="资源不存在或无权访问")
    return {
        "id": str(resume.id),
        "user_id": resume.user_id,
        "parsed": resume.parsed_json,
        "health_check": resume.health_check,
        "raw_text": resume.raw_text,
        "uploaded_at": resume.uploaded_at.isoformat(),
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
    rewrite_mode: str = "standard"


class EvidenceFollowupAnalyzeRequest(BaseModel):
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
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(require_candidate),
    db: AsyncSession = Depends(get_db),
):
    """内嵌简历诊断（无需跳转 Analytics）。"""
    resume = await owned_resume_or_404(db, resume_id, current_user)
    return await run_resume_coach(
        db,
        actor=current_user,
        resume=resume,
        company_id=body.company_id,
        role_family=body.role_family,
        target_job_title=body.target_job_title,
        idempotency_key=idempotency_key or str(uuid.uuid4()),
        entrypoint="resume",
    )


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
    health = resume.health_check or {}
    consistency_issues = (health.get("consistency_diagnosis") or {}).get("issues") or []
    has_consistency_pending = any(
        (s.get("source") == "consistency") or str(s.get("id", "")).startswith("consistency_")
        for s in pending
    )
    needs_sync = (not pending and health) or (consistency_issues and not has_consistency_pending)
    if needs_sync:
        actionable = build_actionable_suggestions(
            resume.parsed_json or {},
            health,
        )
        if actionable:
            pending = await sync_suggestions_for_source(db, resume_id, "health_check", actionable)
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

    stored_row = None
    if body.suggestion_id:
        stored_row = await get_suggestion_by_id(db, body.suggestion_id, resume_id=resume_id)
    elif body.suggestion_key:
        stored_row = await get_suggestion_by_key(db, resume_id, body.suggestion_key)

    stored_dict = None
    if stored_row is not None:
        from .resume_suggestion_store import _row_to_dict

        stored_dict = _row_to_dict(stored_row)

    old_json = copy.deepcopy(resume.parsed_json or {})
    try:
        # 不信任客户端随意改写 action；占位文案一律拒绝
        safe_patch = validate_client_patch_against_stored(
            body.patch,
            stored_dict,
            evidence_completed=bool((body.patch or {}).get("evidence_completed")),
        )
        requires_fidelity_proof = bool(
            (stored_dict or {}).get("requires_evidence")
            or (stored_dict or {}).get("needs_followup")
            or safe_patch.get("evidence_completed")
        )
        fidelity_payload = None
        if requires_fidelity_proof:
            section = safe_patch.get("section")
            index = safe_patch.get("index")
            field = safe_patch.get("field") or "description"
            field_path = (
                f"{section}[{index}].{field}" if index is not None else f"{section}.{field}"
            )
            fidelity_payload = verify_fidelity_proof(
                str(safe_patch.get("fidelity_proof") or ""),
                resume_id=resume_id,
                field_path=field_path,
                value=safe_patch.get("value"),
            )
        new_json = apply_suggestion_patch(old_json, safe_patch)
    except ValueError as e:
        # 失败时不得标记 applied
        raise HTTPException(status_code=400, detail=str(e))

    target_job = await _resolve_target_job(db, resume_id, body.job_id)
    impact = compute_suggestion_impact(
        old_json,
        new_json,
        target_job.parsed_json if target_job else None,
        target_job.title if target_job else "",
    )

    if fidelity_payload:
        history = list(new_json.get("_fidelity_history") or [])
        history.append(
            {
                "field_path": fidelity_payload["field_path"],
                "evidence_references": fidelity_payload.get("evidence_references") or [],
                "fidelity_result": fidelity_payload.get("fidelity_result") or {},
                "applied_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        new_json["_fidelity_history"] = history[-100:]
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

    questions = await run_in_thread(generate_followup_questions, context)
    resume_json = resume.parsed_json or {}
    claim_followup_answers = match_claim_followup_answers(resume_json, context)
    clarification_answers = match_clarification_answers(resume_json, context)
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
        "claim_followup_answers": claim_followup_answers,
        "clarification_answers": clarification_answers,
    }


@app.post("/resumes/{resume_id}/evidence-followup/analyze")
async def evidence_followup_analyze(
    resume_id: str,
    body: EvidenceFollowupAnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """采纳前语义澄清分析：系统如何理解用户回答，不生成最终文本。"""
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该简历")

    try:
        context = get_entry_context(resume.parsed_json or {}, body.entry_type, body.index)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    analysis = analyze_followup_answers(
        context,
        [a.model_dump() for a in body.answers],
    )
    return {
        "resume_id": resume_id,
        "entry_type": body.entry_type,
        "index": body.index,
        "analysis": analysis,
    }


@app.post("/resumes/{resume_id}/evidence-followup/regenerate")
async def evidence_followup_regenerate(
    resume_id: str,
    body: EvidenceFollowupRegenerateRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
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

    reservation = await reserve_feature_entitlement(
        db,
        actor=current_user,
        feature="evidence_regenerate",
        idempotency_key=idempotency_key or str(uuid.uuid4()),
        request_payload={
            "resume_id": resume_id,
            **body.model_dump(),
        },
        reservation_meta={"entrypoint": "evidence_followup"},
    )
    if not reservation["created"]:
        raise HTTPException(
            status_code=409,
            detail={"error": "idempotency_replayed", **reservation},
        )

    try:
        context = get_entry_context(resume.parsed_json or {}, body.entry_type, body.index)
    except ValueError as e:
        await finalize_quota(
            db,
            reservation["reservation_id"],
            succeeded=False,
            failure_reason="invalid_context",
        )
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = await run_in_thread(
            regenerate_evidence_sentence,
            context,
            [a.model_dump() for a in body.answers],
            rewrite_mode=body.rewrite_mode,
        )
    except Exception:
        await db.rollback()
        await finalize_quota(
            db,
            reservation["reservation_id"],
            succeeded=False,
            failure_reason="generation_error",
        )
        raise
    metering = result.pop("_metering", {})
    if metering.get("model_called"):
        await record_provider_cost_event(
            db,
            reservation_id=reservation["reservation_id"],
            user_id=str(current_user.id),
            organization_id=None,
            feature="evidence_regenerate",
            prompt_version="evidence-regenerate-v1",
            provider_status=metering.get("provider_status") or "unknown",
            usage=metering.get("provider_usage"),
        )
    model_output_used = bool(metering.get("model_output_used"))
    await finalize_quota(
        db,
        reservation["reservation_id"],
        succeeded=model_output_used,
        failure_reason=(
            None
            if model_output_used
            else (
                "no_model_call"
                if not metering.get("model_called")
                else "model_output_not_delivered"
            )
        ),
        meta={
            "model_called": bool(metering.get("model_called")),
            "fidelity_version": (result.get("fidelity_result") or {}).get("version"),
            "evidence_references": result.get("evidence_references") or [],
        },
    )
    result["fidelity_proof"] = create_fidelity_proof(
        resume_id=resume_id,
        field_path=result["field_path"],
        value=result["example_after"],
        fidelity_result=result.get("fidelity_result") or {},
        evidence_references=result.get("evidence_references") or [],
    )
    return {
        "resume_id": resume_id,
        **result,
    }


@app.get("/resumes/{resume_id}/claim-followup/questions")
async def claim_followup_questions(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI 面试官：获取简历 claim 追问列表。"""
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该简历")

    parsed = resume.parsed_json or {}
    pack = generate_claim_followup_pack(parsed)
    questions = pack["questions"]
    audit = pack["audit"]
    return {
        "resume_id": resume_id,
        "intro": "为了让这段经历表达得更可信，AI 面试官会帮你补齐细节。",
        "questions": questions,
        "claim_audit_summary": {
            "flagged_claims": audit.get("flagged_claims", 0),
            "overall_status": audit.get("overall_status"),
            "overall_status_label": audit.get("overall_status_label"),
        },
    }


@app.get("/resumes/{resume_id}/claim-reasoning-audit")
async def resume_claim_reasoning_audit(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """求职者侧：claim 级推理审计。"""
    resume = await db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if resume.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该简历")

    audit = await run_in_thread(reason_about_claims, resume.parsed_json or {})
    return {"resume_id": resume_id, "claim_reasoning": audit}


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

    resume_stmt = (
        select(MatchResult)
        .join(Resume, MatchResult.resume_id == Resume.id)
        .where(Resume.user_id == user_id)
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
    await owned_resume_or_404(db, resume_id, current_user)
    await delete_resume_graph(db, [resume_id])
    await db.commit()
    return {"status": "ok"}


# ------------- 岗位发布 ---------------
@app.post("/post-job", response_model=JobInfo)
async def post_job(
    file: Optional[UploadFile] = None,
    description_text: Optional[str] = None,
    current_user: User = Depends(require_employer),
    db: AsyncSession = Depends(get_db),
):
    file_path = None
    if file:
        try:
            file_path, ext = await save_upload_safely(file, UPLOAD_DIR)
            text = await extract_text_bounded(
                file_path,
                ext,
                extract_text_from_pdf,
                extract_text_from_docx,
            )
        finally:
            if file_path is not None:
                file_path.unlink(missing_ok=True)
    elif description_text:
        text = description_text
        max_chars = int(os.getenv("UPLOAD_MAX_TEXT_CHARS", "100000"))
        if len(text) > max_chars:
            raise HTTPException(status_code=413, detail="岗位描述超过长度限制")
    else:
        raise HTTPException(status_code=400, detail="请上传文件或填写 description_text")
    job_data = await call_parser_bounded(parse_job_with_llm, text)
    jd = JobDescription(
        employer_id=str(current_user.id),
        title=job_data.title or "未命名岗位",
        raw_text=text,
        parsed_json=job_data.model_dump(),
    )
    db.add(jd)
    await db.commit()
    return job_data


# ------------- 岗位查询 ---------------
def _owned_job_payload(job: JobDescription) -> dict:
    return {
        "id": str(job.id),
        "title": job.title,
        "parsed": job.parsed_json,
        "created_at": job.created_at.isoformat(),
    }


@app.get("/jobs/mine")
async def get_my_jobs(
    current_user: User = Depends(require_employer),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(JobDescription)
        .where(JobDescription.employer_id == str(current_user.id))
        .order_by(JobDescription.created_at.desc())
    )
    result = await db.execute(stmt)
    return [_owned_job_payload(job) for job in result.scalars().all()]


@app.get("/jobs/{employer_id}")
async def get_jobs(
    employer_id: str,
    current_user: User = Depends(require_employer),
    db: AsyncSession = Depends(get_db),
):
    if employer_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="资源不存在或无权访问")
    return await get_my_jobs(current_user=current_user, db=db)


@app.post("/jobs/sync-sources")
async def sync_job_sources(
    current_user: User = Depends(require_admin),
):
    """Enqueue scrape + analytics rebuild (admin)."""
    accepted = await enqueue_job(
        redis_client,
        job_type="job_sources_sync",
        payload={},
        idempotency_key=f"job_sources_sync:{current_user.id}:{int(time.time()) // 60}",
    )
    return {
        "msg": "岗位与数据分析同步任务已受理",
        "job_id": accepted["job_id"],
        "status": accepted["status"],
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
    db: AsyncSession = Depends(get_db),
):
    stmt = select(JobDescription)
    if keyword:
        like_pattern = f"%{keyword}%"
        stmt = stmt.where(
            (JobDescription.title.ilike(like_pattern))
            | (JobDescription.raw_text.ilike(like_pattern))
        )
    result = await db.execute(stmt.order_by(JobDescription.created_at.desc()))
    jobs = result.scalars().all()

    # 地点过滤
    if location:
        jobs = [
            j for j in jobs if j.parsed_json and location in (j.parsed_json.get("location") or "")
        ]

    # 薪资范围过滤
    def parse_salary_range(salary_str):
        """解析 '25k-35k' 或 '25000-35000' 返回 (最低, 最高) 单位为k"""
        if not salary_str:
            return None
        nums = re.findall(r"[\d.]+", salary_str)
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
        jobs = [j for j in jobs if job_source_type(j.employer_id, j.parsed_json) == source_type]

    if sort_by == "created_at":
        jobs = sorted(jobs, key=lambda j: j.created_at, reverse=True)

    return [
        {
            "id": str(j.id),
            "title": j.title,
            "parsed": public_job_payload(j.parsed_json),
            "company_name": (j.parsed_json or {}).get("company_name", ""),
            "created_at": j.created_at.isoformat(),
            "source": job_source_label(j.employer_id, j.parsed_json),
            "source_type": job_source_type(j.employer_id, j.parsed_json),
        }
        for j in jobs
    ]


# ------------- 岗位编辑 ---------------
class JobUpdate(BaseModel):
    parsed_json: Dict[str, Any]


PUBLIC_JOB_FIELDS = {
    "title",
    "responsibilities",
    "requirements",
    "required_skills",
    "soft_skills",
    "leadership_signals",
    "communication_signals",
    "education_requirement",
    "school_tier_keywords",
    "salary_range",
    "location",
    "experience_years",
    "education",
    "other_notes",
    "company_name",
    "description",
}


def public_job_payload(parsed: Optional[dict]) -> dict:
    source = parsed or {}
    return {key: source[key] for key in PUBLIC_JOB_FIELDS if key in source}


@app.put("/jobs/{job_id}")
async def update_job(
    job_id: str,
    update: JobUpdate,
    current_user: User = Depends(require_employer),
    db: AsyncSession = Depends(get_db),
):
    job = await owned_job_or_404(db, job_id, current_user)
    job.parsed_json = update.parsed_json
    job.title = str(update.parsed_json.get("title") or job.title)
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
        "parsed": public_job_payload(job.parsed_json),
        "company_name": job.parsed_json.get("company_name", "") if job.parsed_json else "",
        "created_at": job.created_at.isoformat(),
    }


# ------------- 岗位删除 ---------------
@app.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    current_user: User = Depends(require_employer),
    db: AsyncSession = Depends(get_db),
):
    await owned_job_or_404(db, job_id, current_user)
    try:
        await delete_job_graph(db, [job_id])
        await db.commit()
        return {"status": "ok"}
    except Exception:
        await db.rollback()
        logger.exception("岗位删除失败 job_id=%s", job_id)
        raise HTTPException(status_code=500, detail="删除失败，请稍后重试")


# ------------- 匹配 ---------------
class MatchEvaluateRequest(BaseModel):
    resume_id: Optional[str] = None
    job_id: Optional[str] = None


@app.post("/match/evaluate")
async def evaluate_match(
    req: MatchEvaluateRequest,
    current_user: User = Depends(require_candidate),
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == "candidate":
        if not resume_id:
            raise HTTPException(status_code=400, detail="求职者必须指定自己的简历")
        await owned_resume_or_404(db, resume_id, current_user)
    elif current_user.role == "employer":
        if not job_id:
            raise HTTPException(status_code=400, detail="招聘方必须指定自己的岗位")
        await owned_job_or_404(db, job_id, current_user)
        if resume_id:
            raise HTTPException(
                status_code=400,
                detail="招聘方不能按任意 resume_id 定向生成匹配",
            )
    elif current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权执行匹配")
    accepted = await enqueue_job(
        redis_client,
        job_type="match_generate",
        payload={
            "resume_id": resume_id,
            "job_id": job_id,
            "force_refresh": True,
            "llm_rerank_top": 0,
        },
        idempotency_key=f"match_generate:{resume_id}:{job_id}",
    )
    return {"status": accepted["status"], "job_id": accepted["job_id"]}


@app.post("/match/user/{user_id}")
async def match_for_user(
    user_id: str,
    use_llm: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "admin" and (
        current_user.role != "candidate" or str(current_user.id) != user_id
    ):
        raise HTTPException(status_code=404, detail="资源不存在或无权访问")
    accepted = await enqueue_job(
        redis_client,
        job_type="match_generate",
        payload={
            "user_id": user_id,
            "force_refresh": True,
            "llm_rerank_top": 5 if use_llm else 0,
        },
        idempotency_key=f"match_generate:user:{user_id}:{int(use_llm)}",
    )
    return {
        "status": accepted["status"],
        "job_id": accepted["job_id"],
        "inline": accepted.get("inline"),
        "result": accepted.get("result"),
    }


@app.get("/matches/user/{user_id}")
async def get_matches_for_user(
    user_id: str,
    refresh: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "admin" and (
        current_user.role != "candidate" or str(current_user.id) != user_id
    ):
        raise HTTPException(status_code=404, detail="资源不存在或无权访问")
    # 如果需要刷新，先入队生成匹配（TESTING 下 inline）
    if refresh:
        await enqueue_job(
            redis_client,
            job_type="match_generate",
            payload={
                "user_id": user_id,
                "force_refresh": True,
                "llm_rerank_top": 5,
            },
            idempotency_key=f"match_generate:user:{user_id}:refresh",
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
        .limit(100)  # 最多 100 个
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
            "job_location": job_map[str(m.job_id)].parsed_json.get("location")
            if str(m.job_id) in job_map
            else None,
            "job_salary": job_map[str(m.job_id)].parsed_json.get("salary_range")
            if str(m.job_id) in job_map
            else None,
            "created_at": m.created_at.isoformat(),
        }

    return [_serialize_user_match(m) for m in matches]


@app.get("/matches/resume/{resume_id}")
async def get_matches_for_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await owned_resume_or_404(db, resume_id, current_user)
    stmt = (
        select(MatchResult)
        .where(MatchResult.resume_id == resume_id)
        .order_by(MatchResult.score.desc())
    )
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
            "created_at": m.created_at.isoformat(),
        }
        for m in matches
    ]


@app.get("/matches/job/{job_id}")
async def get_matches_for_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in {"employer", "admin"}:
        raise HTTPException(status_code=403, detail="仅招聘方可查看岗位匹配")
    await owned_job_or_404(db, job_id, current_user)
    stmt = (
        select(MatchResult).where(MatchResult.job_id == job_id).order_by(MatchResult.score.desc())
    )
    result = await db.execute(stmt)
    matches = result.scalars().all()

    if current_user.role != "admin":
        application_stmt = select(JobApplication).where(
            JobApplication.job_id == job_id,
            JobApplication.employer_id == str(current_user.id),
        )
        applications = (await db.execute(application_stmt)).scalars().all()
        authorized_resume_ids = {
            str(application.resume_id)
            for application in applications
            if application_has_candidate_authorization(application)
        }
        matches = [match for match in matches if str(match.resume_id) in authorized_resume_ids]

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
            "candidate_name": (
                resume_map[str(m.resume_id)].parsed_json.get("name")
                if str(m.resume_id) in resume_map
                else None
            )
            or "匿名",
            "expected_title": (
                resume_map[str(m.resume_id)].parsed_json.get("expected_job_title")
                if str(m.resume_id) in resume_map
                else None
            )
            or "未填写",
            "created_at": m.created_at.isoformat(),
        }
        for m in matches
    ]


# ------------- 虚拟面试官 ---------------
# 鉴权优先：首条 JSON {"type":"auth","token":"..."}；query token 默认关闭。
@app.websocket("/ws/interview/{user_id}")
async def websocket_interview(websocket: WebSocket, user_id: str):
    requested_mode = websocket.query_params.get("mode", "profile")
    mode = requested_mode if requested_mode in {"profile", "claim_followup"} else "profile"
    resume_id = websocket.query_params.get("resume_id")
    application_id = websocket.query_params.get("application_id")
    await websocket.accept()

    async with AsyncSessionLocal() as db:
        user = await authenticate_websocket(
            websocket,
            db,
            user_id=user_id,
            resume_id=resume_id,
            application_id=application_id,
        )
        if user is None:
            return

        try:
            fair_use = await start_interview_session(
                db,
                actor=user,
                mode=mode,
            )
        except HTTPException as exc:
            await send_fair_use_error(websocket, exc)
            await websocket.close(code=1008, reason="fair_use_exceeded")
            return

        try:
            if mode == "claim_followup" and resume_id:
                await claim_followup_handler(
                    websocket,
                    user_id,
                    resume_id,
                    db,
                    application_id=application_id,
                    fair_use=fair_use,
                )
            else:
                await interview_handler(
                    websocket,
                    user_id,
                    db,
                    application_id=application_id,
                    fair_use=fair_use,
                )
        finally:
            await close_interview_session(db, fair_use)


@app.get("/usage/me")
async def my_usage(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """当前用户本月功能额度；供应商 token 与成本仅管理员可见。"""
    return await get_usage_summary(db, str(current_user.id))


# ------------- 健康检查 ---------------
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    result = await collect_readiness(engine, redis_client)
    if result["status"] != "ready":
        raise HTTPException(
            status_code=503,
            detail={"code": "service_not_ready", "message": "服务尚未就绪"},
        )
    return {
        "status": "ready",
        "model_mode": model_runtime_mode(),
    }


@app.get("/admin/readiness")
async def admin_readiness(
    _current_user: User = Depends(require_admin),
):
    return await collect_readiness(engine, redis_client)
