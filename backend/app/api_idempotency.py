"""Unified Idempotency-Key replay ledger for PR11 write APIs."""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Callable

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .models_db import ApiIdempotencyKey


def _now() -> datetime:
    return datetime.now(timezone.utc)


def fingerprint_payload(payload: Any) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_idempotency_key(key: str | None) -> str | None:
    if key is None:
        return None
    value = key.strip()
    if not value:
        return None
    if len(value) > 128:
        raise HTTPException(status_code=422, detail="Idempotency-Key 必须为 1-128 字符")
    return value


@dataclass
class IdempotencyGate:
    replay: dict[str, Any] | None = None
    _persist: Callable[[int, dict[str, Any]], None] | None = field(default=None, repr=False)

    def set_response(self, status_code: int, body: dict[str, Any]) -> None:
        """Register success body and stage ledger row before the handler commits."""
        if self._persist is None:
            return
        self._persist(int(status_code), body)


@asynccontextmanager
async def idempotent_write(
    db: AsyncSession,
    *,
    user_id: str,
    scope: str,
    idempotency_key: str | None,
    request_payload: Any,
    ttl_hours: int = 24,
) -> AsyncIterator[IdempotencyGate]:
    """Replay-safe write gate.

    - Missing key: pass-through (no ledger), compatible with older clients.
    - Same key + same fingerprint: replay stored JSON body.
    - Same key + different fingerprint: 409 idempotency_conflict.

    Handlers must call ``gate.set_response`` before ``db.commit`` so the ledger
    row is flushed in the same transaction as the business write.
    """
    key = normalize_idempotency_key(idempotency_key)
    gate = IdempotencyGate()
    if not key:
        yield gate
        return

    fingerprint = fingerprint_payload(request_payload)
    lock_name = f"api_idem:{user_id}:{scope}:{key}"

    if db.bind and db.bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": lock_name[:64]},
        )

    existing = (
        await db.execute(
            select(ApiIdempotencyKey).where(
                ApiIdempotencyKey.user_id == str(user_id),
                ApiIdempotencyKey.scope == scope,
                ApiIdempotencyKey.idempotency_key == key,
            )
        )
    ).scalar_one_or_none()

    if existing:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(
                status_code=409,
                detail={"error": "idempotency_conflict", "scope": scope},
            )
        gate.replay = existing.response_body or {}
        yield gate
        return

    def _persist(status_code: int, body: dict[str, Any]) -> None:
        db.add(
            ApiIdempotencyKey(
                id=str(uuid.uuid4()),
                user_id=str(user_id),
                scope=scope,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                response_status=status_code,
                response_body=body,
                expires_at=_now() + timedelta(hours=ttl_hours),
            )
        )

    gate._persist = _persist
    yield gate
