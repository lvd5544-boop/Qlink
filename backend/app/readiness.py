"""Dependency readiness checks without exposing credentials or cost data."""

from __future__ import annotations

import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from .ai.config import ai_enabled, primary_api_key, provider_configured
from .schema_version import inspect_schema, schema_version_required


def model_runtime_mode() -> str:
    if not ai_enabled():
        return "rules_only"
    return "provider" if provider_configured() else "rules_only"


def _model_required() -> bool:
    return os.getenv("MODEL_REQUIRED", "").strip().lower() in {"1", "true", "yes"}


async def collect_readiness(engine: AsyncEngine, redis_client) -> dict:
    checks: dict[str, dict] = {}
    redis_ok = False

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:
        checks["database"] = {
            "ok": False,
            "reason": type(exc).__name__,
        }

    try:
        if redis_client is None:
            raise RuntimeError("not_configured")
        await redis_client.ping()
        checks["redis"] = {"ok": True}
        redis_ok = True
    except Exception as exc:
        checks["redis"] = {
            "ok": False,
            "reason": str(exc) if str(exc) == "not_configured" else type(exc).__name__,
        }

    require_background = os.getenv("REQUIRE_BACKGROUND_HEARTBEATS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if redis_ok:
        worker = await redis_client.get("ai-job-platform:worker-heartbeat")
        scheduler = await redis_client.get("ai-job-platform:scheduler-heartbeat")
        checks["background"] = {
            "ok": (bool(worker) and bool(scheduler)) or not require_background,
            "required": require_background,
            "worker": "online" if worker else "offline",
            "scheduler": "online" if scheduler else "offline",
        }
    else:
        checks["background"] = {
            "ok": not require_background,
            "required": require_background,
            "worker": "unknown",
            "scheduler": "unknown",
        }

    try:
        status = await inspect_schema(engine)
        required = schema_version_required()
        checks["schema"] = {
            "ok": status.ready or not required,
            "required": required,
            "missing": list(status.missing),
        }
    except Exception as exc:
        checks["schema"] = {
            "ok": not schema_version_required(),
            "required": schema_version_required(),
            "reason": type(exc).__name__,
        }

    model_mode = model_runtime_mode()
    checks["model"] = {
        "ok": model_mode == "provider" or not _model_required(),
        "mode": model_mode,
        "required": _model_required(),
        "ai_enabled": ai_enabled(),
        "reason": (
            None
            if model_mode == "provider"
            else "ai_disabled"
            if not ai_enabled()
            else "api_key_missing"
            if not primary_api_key()
            else "provider_unavailable"
        ),
    }
    ready = all(item["ok"] for item in checks.values())
    return {"status": "ready" if ready else "not_ready", "checks": checks}
