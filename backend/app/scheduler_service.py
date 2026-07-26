"""Dedicated scheduler process; never import this into web worker startup."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import redis.asyncio as aioredis

from .database import AsyncSessionLocal, engine
from .foreign_job_fetcher import fetch_foreign_jobs
from .guoqi_job_fetcher import fetch_guoqi_jobs
from .market_analytics import (
    rebuild_hired_benchmarks_statistical,
    run_full_analytics_rebuild,
)
from .matching import generate_matches_auto
from .schema_version import require_current_schema

logger = logging.getLogger(__name__)
_redis = None


async def _weekly_forum_sync() -> None:
    from .forum_insight_pipeline import sync_forum_insights_to_db

    async with AsyncSessionLocal() as db:
        await sync_forum_insights_to_db(db)
        await rebuild_hired_benchmarks_statistical(db)


async def _run_locked(
    job_id: str,
    function,
    *,
    kwargs: dict | None = None,
) -> None:
    """Prevent duplicate execution if a scheduler replica is started."""
    if _redis is None:
        raise RuntimeError("scheduler Redis lock is unavailable")
    token = str(uuid.uuid4())
    key = f"scheduler-lock:{job_id}"
    acquired = await _redis.set(key, token, ex=6 * 60 * 60, nx=True)
    if not acquired:
        logger.info("跳过已被其他实例持有的任务 %s", job_id)
        return
    try:
        result = function(**(kwargs or {}))
        if asyncio.iscoroutine(result):
            await result
    finally:
        await _redis.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            key,
            token,
        )


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        _run_locked,
        "cron",
        args=("weekly_foreign_job_fetch", fetch_foreign_jobs),
        day_of_week="mon",
        hour=2,
        id="weekly_foreign_job_fetch",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_locked,
        "cron",
        args=("weekly_guoqi_job_fetch", fetch_guoqi_jobs),
        day_of_week="mon",
        hour=4,
        id="weekly_guoqi_job_fetch",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_locked,
        "cron",
        args=("weekly_llm_match", generate_matches_auto),
        day_of_week="sun",
        hour=3,
        kwargs={"kwargs": {"llm_rerank_top": 20}},
        id="weekly_llm_match",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_locked,
        "cron",
        args=("weekly_analytics_rebuild", run_full_analytics_rebuild),
        day_of_week="sun",
        hour=5,
        id="weekly_analytics_rebuild",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_locked,
        "cron",
        args=("weekly_forum_insight_sync", _weekly_forum_sync),
        day_of_week="wed",
        hour=3,
        id="weekly_forum_insight_sync",
        replace_existing=True,
    )
    return scheduler


async def run_scheduler() -> None:
    global _redis
    await require_current_schema(engine)
    _redis = aioredis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )
    await _redis.ping()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    scheduler = build_scheduler()
    scheduler.start()
    logger.info("独立调度器已启动，时区 Asia/Shanghai")

    async def heartbeat() -> None:
        while not stop.is_set():
            await _redis.set(
                "ai-job-platform:scheduler-heartbeat",
                "online",
                ex=30,
            )
            try:
                await asyncio.wait_for(stop.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        await stop.wait()
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        scheduler.shutdown(wait=False)
        await _redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_scheduler())
