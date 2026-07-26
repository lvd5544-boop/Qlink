"""Redis Stream-backed background jobs for work that must not run in web."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
import uuid
from typing import Any

import redis.asyncio as aioredis

from .database import AsyncSessionLocal, engine
from .schema_version import require_current_schema

logger = logging.getLogger(__name__)

STREAM = "ai-job-platform:background-jobs"
DEAD_LETTER_STREAM = "ai-job-platform:background-jobs-dlq"
GROUP = "ai-job-platform-workers"
MAX_ATTEMPTS = int(os.getenv("BACKGROUND_JOB_MAX_ATTEMPTS", "3"))
IDEMPOTENCY_TTL_SECONDS = int(os.getenv("BACKGROUND_JOB_IDEMPOTENCY_TTL", "3600"))
PENDING_CLAIM_IDLE_MS = int(os.getenv("BACKGROUND_JOB_PENDING_CLAIM_IDLE_MS", "60000"))
PENDING_CLAIM_INTERVAL_SECONDS = int(
    os.getenv("BACKGROUND_JOB_PENDING_CLAIM_INTERVAL_SECONDS", "30")
)
JOB_STATUS_TTL_SECONDS = int(os.getenv("BACKGROUND_JOB_STATUS_TTL", "86400"))

_shared_redis = None


def bind_redis(client) -> None:
    """Allow web process to share its Redis handle with enqueue helpers."""
    global _shared_redis
    _shared_redis = client


def shared_redis():
    return _shared_redis


def _jobs_inline() -> bool:
    """Explicit inline mode for tests that want handlers without a worker."""
    configured = os.getenv("BACKGROUND_JOBS_INLINE", "").strip().lower()
    if configured:
        return configured in {"1", "true", "yes"}
    # When Redis is unavailable, callers still may run inline (see enqueue_job).
    return False


def _status_key(job_id: str) -> str:
    return f"ai-job-platform:job-status:{job_id}"


def _idempotency_redis_key(idempotency_key: str) -> str:
    return f"ai-job-platform:job-done:{idempotency_key}"


async def _set_status(redis_client, job_id: str, **fields: Any) -> None:
    if redis_client is None:
        return
    payload = {k: json.dumps(v, ensure_ascii=False) for k, v in fields.items()}
    payload["updated_at"] = str(int(time.time()))
    await redis_client.hset(_status_key(job_id), mapping=payload)
    await redis_client.expire(_status_key(job_id), JOB_STATUS_TTL_SECONDS)


async def get_job_status(redis_client, job_id: str) -> dict[str, Any] | None:
    if redis_client is None:
        return None
    raw = await redis_client.hgetall(_status_key(job_id))
    if not raw:
        return None
    out: dict[str, Any] = {"job_id": job_id}
    for key, value in raw.items():
        try:
            out[key] = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            out[key] = value
    return out


async def enqueue_job(
    redis_client,
    *,
    job_type: str,
    payload: dict,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Enqueue a background job or run inline when Redis/queue is disabled."""
    job_id = str(uuid.uuid4())
    idem = idempotency_key or f"{job_type}:{job_id}"
    fields = {
        "type": job_type,
        "payload": json.dumps(payload),
        "attempt": "0",
        "idempotency_key": idem,
        "job_id": job_id,
    }

    if redis_client is None or _jobs_inline():
        await _set_status(
            redis_client,
            job_id,
            status="running",
            type=job_type,
            payload=payload,
        )
        try:
            result = await _handle(fields)
            await _set_status(
                redis_client,
                job_id,
                status="succeeded",
                type=job_type,
                result=result or {},
            )
            return {
                "job_id": job_id,
                "status": "succeeded",
                "inline": True,
                "result": result or {},
            }
        except Exception as exc:
            await _set_status(
                redis_client,
                job_id,
                status="failed",
                type=job_type,
                error=str(exc)[:1000],
            )
            raise

    message_id = await redis_client.xadd(
        STREAM,
        fields,
        maxlen=10000,
        approximate=True,
    )
    await _set_status(
        redis_client,
        job_id,
        status="queued",
        type=job_type,
        payload=payload,
        message_id=str(message_id),
    )
    return {
        "job_id": job_id,
        "status": "queued",
        "inline": False,
        "message_id": str(message_id),
    }


async def enqueue_resume_match(redis_client, resume_id: str) -> str:
    result = await enqueue_job(
        redis_client,
        job_type="resume_match",
        payload={"resume_id": str(resume_id)},
        idempotency_key=f"resume_match:{resume_id}",
    )
    return str(result["job_id"])


async def _run_resume_match(payload: dict) -> dict:
    from .matching import generate_matches

    resume_id = str(payload["resume_id"])
    async with AsyncSessionLocal() as db:
        await generate_matches(
            db,
            resume_id=resume_id,
            force_refresh=True,
            llm_rerank_top=int(payload.get("llm_rerank_top") or 3),
        )
    logger.info("后台匹配完成 resume_id=%s", resume_id)
    return {"resume_id": resume_id}


async def _run_match_generate(payload: dict) -> dict:
    from .matching import generate_matches, generate_matches_for_user

    async with AsyncSessionLocal() as db:
        if payload.get("user_id"):
            n = await generate_matches_for_user(
                db,
                str(payload["user_id"]),
                force_refresh=bool(payload.get("force_refresh", True)),
                llm_rerank_top=int(payload.get("llm_rerank_top") or 5),
            )
            return {"resumes_processed": n, "user_id": str(payload["user_id"])}
        await generate_matches(
            db,
            resume_id=payload.get("resume_id"),
            job_id=payload.get("job_id"),
            force_refresh=bool(payload.get("force_refresh", True)),
            llm_rerank_top=int(payload.get("llm_rerank_top") or 0),
        )
    return {
        "resume_id": payload.get("resume_id"),
        "job_id": payload.get("job_id"),
    }


async def _run_job_sources_sync(_payload: dict) -> dict:
    from .foreign_job_fetcher import fetch_foreign_jobs
    from .guoqi_job_fetcher import fetch_guoqi_jobs
    from .market_analytics import run_full_analytics_rebuild

    await fetch_foreign_jobs()
    await fetch_guoqi_jobs()
    await run_full_analytics_rebuild()
    return {
        "sources": ["国企-国资央企", "外企-Remotive/Arbeitnow", "录用画像-网络论坛统计"],
    }


async def _run_analytics_rebuild(payload: dict) -> dict:
    from .company_registry import seed_companies
    from .forum_insight_pipeline import sync_forum_insights_to_db
    from .market_analytics import (
        rebuild_hired_benchmarks_statistical,
        rebuild_market_insights,
        run_full_analytics_rebuild,
    )

    if payload.get("full"):
        await run_full_analytics_rebuild()
        return {"rebuilt": True, "mode": "full"}

    async with AsyncSessionLocal() as db:
        if payload.get("seed_companies"):
            await seed_companies(db)
        forum_stats = await sync_forum_insights_to_db(db)
        jd_count = await rebuild_market_insights(db)
        hb_count = await rebuild_hired_benchmarks_statistical(db)
    return {
        "rebuilt": True,
        "forum": forum_stats,
        "market_insights": jd_count,
        "hired_benchmarks": hb_count,
    }


async def _run_forum_sync(_payload: dict) -> dict:
    from .forum_insight_pipeline import sync_forum_insights_to_db
    from .market_analytics import rebuild_hired_benchmarks_statistical

    async with AsyncSessionLocal() as db:
        synced = await sync_forum_insights_to_db(db)
        written = await rebuild_hired_benchmarks_statistical(db)
    return {"synced": synced, "benchmarks_written": written}


async def _run_llm_parse(payload: dict) -> dict:
    """Parse resume or job text via LLM off the web process."""
    from .job_parser import parse_job_with_llm
    from .llm_client import run_in_thread
    from .resume_parser import parse_with_llm

    kind = str(payload.get("kind") or "resume")
    text = str(payload.get("text") or "")
    if kind == "job":
        parsed = await run_in_thread(parse_job_with_llm, text)
    else:
        parsed = await run_in_thread(parse_with_llm, text)
    return {"kind": kind, "parsed": parsed}


async def _handle(fields: dict) -> dict | None:
    job_type = fields.get("type")
    payload = json.loads(fields.get("payload") or "{}")
    handlers = {
        "resume_match": _run_resume_match,
        "match_generate": _run_match_generate,
        "job_sources_sync": _run_job_sources_sync,
        "analytics_rebuild": _run_analytics_rebuild,
        "forum_sync": _run_forum_sync,
        "llm_parse": _run_llm_parse,
    }
    handler = handlers.get(str(job_type))
    if handler is None:
        raise ValueError(f"unknown background job type: {job_type}")
    return await handler(payload)


async def _requeue_or_dead_letter(
    redis_client,
    *,
    message_id: str,
    fields: dict,
    attempt: int,
    error: str,
) -> None:
    """Atomically retry/park and acknowledge the failed delivery."""
    job_id = fields.get("job_id")
    if attempt < MAX_ATTEMPTS:
        target_stream = STREAM
        target_fields = {
            **fields,
            "attempt": str(attempt),
            "last_error": error[:500],
            "retried_at": str(int(time.time())),
        }
    else:
        target_stream = DEAD_LETTER_STREAM
        target_fields = {
            **fields,
            "attempt": str(attempt),
            "failed_at": str(int(time.time())),
            "last_error": error[:1000],
            "original_message_id": message_id,
        }

    async with redis_client.pipeline(transaction=True) as pipeline:
        pipeline.xadd(
            target_stream,
            target_fields,
            maxlen=10000 if target_stream == STREAM else 5000,
            approximate=True,
        )
        pipeline.xack(STREAM, GROUP, message_id)
        await pipeline.execute()

    if job_id:
        await _set_status(
            redis_client,
            str(job_id),
            status="queued" if target_stream == STREAM else "dead_letter",
            error=error[:1000],
            attempt=attempt,
        )

    if target_stream == STREAM:
        logger.warning(
            "后台任务将重试 message_id=%s attempt=%s/%s",
            message_id,
            attempt,
            MAX_ATTEMPTS,
        )
        return

    logger.error(
        "后台任务进入死信队列 message_id=%s attempt=%s",
        message_id,
        attempt,
    )


async def _mark_done_and_ack(
    redis_client,
    *,
    message_id: str,
    idempotency_key: str,
    job_id: str | None,
    result: dict | None,
) -> None:
    async with redis_client.pipeline(transaction=True) as pipeline:
        pipeline.set(
            _idempotency_redis_key(idempotency_key),
            message_id,
            ex=IDEMPOTENCY_TTL_SECONDS,
        )
        pipeline.xack(STREAM, GROUP, message_id)
        await pipeline.execute()
    if job_id:
        await _set_status(
            redis_client,
            job_id,
            status="succeeded",
            result=result or {},
        )


async def _claim_stale_messages(redis_client, consumer: str) -> list[tuple[str, dict]]:
    result = await redis_client.xautoclaim(
        STREAM,
        GROUP,
        consumer,
        min_idle_time=PENDING_CLAIM_IDLE_MS,
        start_id="0-0",
        count=10,
    )
    if not result or len(result) < 2:
        return []
    return list(result[1])


async def _process_message(redis_client, message_id: str, fields: dict) -> None:
    attempt = int(fields.get("attempt") or "0") + 1
    idempotency_key = fields.get("idempotency_key") or ""
    job_id = fields.get("job_id")
    if job_id:
        await _set_status(redis_client, str(job_id), status="running", attempt=attempt)
    if idempotency_key:
        done_key = _idempotency_redis_key(str(idempotency_key))
        already = await redis_client.get(done_key)
        if already:
            logger.info(
                "跳过已完成的幂等任务 key=%s message_id=%s",
                idempotency_key,
                message_id,
            )
            await redis_client.xack(STREAM, GROUP, message_id)
            if job_id:
                await _set_status(
                    redis_client,
                    str(job_id),
                    status="succeeded",
                    deduplicated=True,
                )
            return

    try:
        result = await _handle(fields)
    except Exception as exc:
        logger.exception("后台任务失败 message_id=%s attempt=%s", message_id, attempt)
        await _requeue_or_dead_letter(
            redis_client,
            message_id=message_id,
            fields=fields,
            attempt=attempt,
            error=str(exc),
        )
        return

    if idempotency_key:
        await _mark_done_and_ack(
            redis_client,
            message_id=message_id,
            idempotency_key=str(idempotency_key),
            job_id=str(job_id) if job_id else None,
            result=result if isinstance(result, dict) else {},
        )
    else:
        await redis_client.xack(STREAM, GROUP, message_id)
        if job_id:
            await _set_status(
                redis_client,
                str(job_id),
                status="succeeded",
                result=result if isinstance(result, dict) else {},
            )


async def run_worker() -> None:
    await require_current_schema(engine)
    # socket_timeout must exceed XREADGROUP block; otherwise idle polls crash the worker.
    redis_client = aioredis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=20,
    )
    await redis_client.ping()
    try:
        await redis_client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    consumer = f"worker-{os.getpid()}"
    next_pending_claim_at = 0.0
    logger.info("后台 worker 已启动 consumer=%s max_attempts=%s", consumer, MAX_ATTEMPTS)

    try:
        while not stop.is_set():
            await redis_client.set(
                "ai-job-platform:worker-heartbeat",
                consumer,
                ex=30,
            )
            now = time.monotonic()
            if now >= next_pending_claim_at:
                claimed = await _claim_stale_messages(redis_client, consumer)
                for message_id, fields in claimed:
                    await _process_message(redis_client, message_id, fields)
                next_pending_claim_at = now + PENDING_CLAIM_INTERVAL_SECONDS
            try:
                messages = await redis_client.xreadgroup(
                    GROUP,
                    consumer,
                    {STREAM: ">"},
                    count=1,
                    block=10000,
                )
            except (TimeoutError, asyncio.TimeoutError, aioredis.TimeoutError):
                continue
            if not messages:
                continue
            for _stream, entries in messages:
                for message_id, fields in entries:
                    await _process_message(redis_client, message_id, fields)
    finally:
        # redis-py async client exposes close(); types-redis stubs may omit aclose().
        close = getattr(redis_client, "aclose", None) or redis_client.close
        await close()
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
