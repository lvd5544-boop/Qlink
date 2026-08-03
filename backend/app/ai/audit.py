"""In-memory / optional DB audit for AI invocations (no raw PII by default)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import audit_content_logging, data_region
from .privacy_filter import hash_payload, redact_text

logger = logging.getLogger(__name__)

_RECENT: list[dict[str, Any]] = []


@dataclass
class InvocationRecord:
    task_type: str
    provider: str
    model_alias: str
    model_id: str
    prompt_version: str
    schema_version: str
    input_hash: str
    status: str
    error_category: str | None = None
    user_id: str | None = None
    org_id: str | None = None
    latency_ms: int | None = None
    token_input: int | None = None
    token_output: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    content_preview: str | None = None


def record_invocation(record: InvocationRecord) -> dict[str, Any]:
    payload = {
        "task_type": record.task_type,
        "provider": record.provider,
        "model_alias": record.model_alias,
        "model_id": record.model_id,
        "prompt_version": record.prompt_version,
        "schema_version": record.schema_version,
        "input_hash": record.input_hash,
        "data_region": data_region(),
        "status": record.status,
        "error_category": record.error_category,
        "user_id": record.user_id,
        "org_id": record.org_id,
        "latency_ms": record.latency_ms,
        "token_input": record.token_input,
        "token_output": record.token_output,
        "created_at": record.created_at.isoformat(),
    }
    if audit_content_logging() and record.content_preview:
        payload["content_preview"] = redact_text(record.content_preview)
    _RECENT.append(payload)
    if len(_RECENT) > 200:
        del _RECENT[:-200]
    logger.info(
        "ai_invocation task=%s status=%s model=%s hash=%s",
        record.task_type,
        record.status,
        record.model_id,
        record.input_hash[:12],
    )
    return payload


async def record_invocation_persisted(record: InvocationRecord) -> dict[str, Any]:
    """Record the invocation in memory and persist it to the PR10 audit table."""
    payload = record_invocation(record)
    try:
        from ..database import AsyncAuditSessionLocal
        from ..models_db import AIInvocation

        async with AsyncAuditSessionLocal() as session:
            session.add(
                AIInvocation(
                    task_type=record.task_type,
                    provider=record.provider,
                    model_alias=record.model_alias,
                    model_id=record.model_id,
                    prompt_version=record.prompt_version,
                    schema_version=record.schema_version,
                    input_snapshot_hash=record.input_hash,
                    data_region=payload["data_region"],
                    token_input=record.token_input,
                    token_output=record.token_output,
                    latency_ms=record.latency_ms,
                    status=record.status,
                    error_category=record.error_category,
                    user_id=record.user_id,
                    org_id=record.org_id,
                )
            )
            await session.commit()
    except Exception:
        # Availability of the user-facing feature must not depend on the audit
        # sink. Production readiness still exposes database/schema failures.
        logger.exception(
            "failed to persist ai_invocation task=%s status=%s",
            record.task_type,
            record.status,
        )
    return payload


def recent_invocations(limit: int = 50) -> list[dict[str, Any]]:
    return list(_RECENT[-limit:])


def input_snapshot_hash(payload: Any) -> str:
    return hash_payload(payload)
