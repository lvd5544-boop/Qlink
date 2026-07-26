"""Persistent fair-use limits for free AI interview sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
import uuid
from zoneinfo import ZoneInfo

from fastapi import HTTPException, WebSocket
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from .billing_accounts import resolve_billing_entitlement
from .models_db import InterviewUsageSession, User


_local_session_locks: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True)
class InterviewFairUse:
    session_id: str
    daily_session_limit: int
    turn_limit: int
    local_day: str


def local_day_key(now: datetime | None = None) -> str:
    timezone_name = os.getenv("BILLING_TIMEZONE", "Asia/Shanghai")
    try:
        billing_timezone = ZoneInfo(timezone_name)
    except Exception as exc:
        raise RuntimeError(f"无效 BILLING_TIMEZONE: {timezone_name}") from exc
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(billing_timezone).strftime("%Y-%m-%d")


def _fair_use_error(limit_type: str, *, limit: int, used: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "error": "fair_use_exceeded",
            "feature": "ai_interview",
            "limit_type": limit_type,
            "limit": limit,
            "used": used,
        },
    )


async def start_interview_session(
    db: AsyncSession,
    *,
    actor: User,
    mode: str,
    now: datetime | None = None,
) -> InterviewFairUse:
    if actor.role != "candidate":
        raise HTTPException(
            status_code=403,
            detail={"error": "candidate_interview_only"},
        )
    session_entitlement = await resolve_billing_entitlement(
        db,
        actor=actor,
        feature="interview_session",
        now=now,
    )
    turn_entitlement = await resolve_billing_entitlement(
        db,
        actor=actor,
        feature="interview_turn",
        now=now,
    )
    if (
        session_entitlement.meter_type != "fair_use"
        or session_entitlement.period != "day"
        or session_entitlement.limit_units is None
        or turn_entitlement.meter_type != "fair_use"
        or turn_entitlement.period != "session"
        or turn_entitlement.limit_units is None
    ):
        raise HTTPException(
            status_code=409,
            detail={"error": "interview_fair_use_misconfigured"},
        )

    user_id = str(actor.id)
    day = local_day_key(now)
    lock_key = f"interview-session:{user_id}:{day}"
    local_lock = _local_session_locks.setdefault(lock_key, asyncio.Lock())
    async with local_lock:
        if db.bind and db.bind.dialect.name == "postgresql":
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": lock_key},
            )

        stale_before = (now or datetime.now(timezone.utc)) - timedelta(
            seconds=max(
                60,
                int(os.getenv("INTERVIEW_ACTIVE_SESSION_TTL_SECONDS", "7200")),
            )
        )
        await db.execute(
            update(InterviewUsageSession)
            .where(
                InterviewUsageSession.user_id == user_id,
                InterviewUsageSession.status == "active",
                InterviewUsageSession.last_activity_at < stale_before,
            )
            .values(
                status="abandoned",
                ended_at=now or datetime.now(timezone.utc),
            )
        )
        active_count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(InterviewUsageSession)
                    .where(
                        InterviewUsageSession.user_id == user_id,
                        InterviewUsageSession.status == "active",
                    )
                )
            ).scalar()
            or 0
        )
        if active_count >= 1:
            await db.rollback()
            raise _fair_use_error(
                "active_connections",
                limit=1,
                used=active_count,
            )

        used_today = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(InterviewUsageSession)
                    .where(
                        InterviewUsageSession.user_id == user_id,
                        InterviewUsageSession.local_day == day,
                    )
                )
            ).scalar()
            or 0
        )
        daily_limit = int(session_entitlement.limit_units)
        if used_today >= daily_limit:
            await db.rollback()
            raise _fair_use_error(
                "daily_sessions",
                limit=daily_limit,
                used=used_today,
            )

        row = InterviewUsageSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
            local_day=day,
            mode=mode,
            turn_count=0,
            status="active",
            last_activity_at=now or datetime.now(timezone.utc),
        )
        db.add(row)
        await db.commit()
        return InterviewFairUse(
            session_id=str(row.id),
            daily_session_limit=daily_limit,
            turn_limit=int(turn_entitlement.limit_units),
            local_day=day,
        )


async def consume_interview_turn(
    db: AsyncSession,
    fair_use: InterviewFairUse,
) -> int:
    row = (
        await db.execute(
            select(InterviewUsageSession)
            .where(InterviewUsageSession.id == fair_use.session_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not row or row.status != "active":
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"error": "interview_session_inactive"},
        )
    used = int(row.turn_count or 0)
    if used >= fair_use.turn_limit:
        await db.rollback()
        raise _fair_use_error(
            "session_turns",
            limit=fair_use.turn_limit,
            used=used,
        )
    row.turn_count = used + 1
    row.last_activity_at = datetime.now(timezone.utc)
    await db.commit()
    return row.turn_count


async def close_interview_session(
    db: AsyncSession,
    fair_use: InterviewFairUse,
    *,
    abandoned: bool = False,
) -> None:
    row = await db.get(InterviewUsageSession, fair_use.session_id)
    if not row or row.status != "active":
        return
    row.status = "abandoned" if abandoned else "closed"
    row.ended_at = datetime.now(timezone.utc)
    row.last_activity_at = row.ended_at
    await db.commit()


async def send_fair_use_error(
    websocket: WebSocket,
    exc: HTTPException,
) -> None:
    detail = (
        exc.detail
        if isinstance(exc.detail, dict)
        else {
            "error": "fair_use_exceeded",
            "message": str(exc.detail),
        }
    )
    await websocket.send_text(json.dumps({"type": "error", **detail}, ensure_ascii=False))
