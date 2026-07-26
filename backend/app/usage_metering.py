"""试点计费：LLM / 审计 / 忠实扩写配额与成本日志。"""

from __future__ import annotations

import os
import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, func, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

_sqlite_reservation_locks: dict[str, asyncio.Lock] = {}


def metering_enabled() -> bool:
    return os.getenv("METERING_ENABLED", "true").lower() in ("1", "true", "yes")


def _month_key(dt: Optional[datetime] = None) -> str:
    timezone_name = os.getenv("BILLING_TIMEZONE", "Asia/Shanghai")
    try:
        billing_timezone = ZoneInfo(timezone_name)
    except Exception as exc:
        raise RuntimeError(f"无效 BILLING_TIMEZONE: {timezone_name}") from exc
    d = dt or datetime.now(timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    d = d.astimezone(billing_timezone)
    return d.strftime("%Y-%m")


def _request_fingerprint(meta: Optional[dict]) -> str:
    encoded = json.dumps(
        meta or {},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reservation_payload(row, *, created: bool) -> dict:
    return {
        "reservation_id": str(row.id),
        "idempotency_key": row.idempotency_key,
        "feature": row.feature,
        "status": row.status,
        "reserved_units": row.reserved_units,
        "created": created,
        "billing_account_type": row.billing_account_type,
        "billing_account_id": row.billing_account_id,
        "period_key": row.period_key,
    }


async def _find_reservation(
    db: AsyncSession,
    *,
    billing_account_type: str,
    billing_account_id: str,
    feature: str,
    period_key: str,
    idempotency_key: str,
    for_update: bool = False,
):
    from .models_db import UsageReservation

    stmt = (
        select(UsageReservation)
        .where(
            UsageReservation.billing_account_type == billing_account_type,
            UsageReservation.billing_account_id == billing_account_id,
            UsageReservation.feature == feature,
            UsageReservation.period_key == period_key,
            UsageReservation.idempotency_key == idempotency_key,
        )
        .order_by(UsageReservation.attempt.desc())
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalars().first()


async def reserve_quota(
    db: AsyncSession,
    *,
    user_id: str,
    feature: str,
    idempotency_key: str,
    units: int = 1,
    meta: Optional[dict] = None,
    billing_account_type: str = "user",
    billing_account_id: Optional[str] = None,
    period_key: Optional[str] = None,
    quota_override: Optional[int] = None,
    request_fingerprint: Optional[str] = None,
) -> dict:
    """在昂贵工作前原子预占额度。

    成功或仍在执行的相同幂等键只返回原记录；已明确失败并释放的记录允许
    使用同一键重新预占，避免安全重试被误判为 replay 冲突。
    """
    from .models_db import UsageEvent, UsageReservation

    key = (idempotency_key or "").strip()
    if not key or len(key) > 128:
        raise HTTPException(status_code=422, detail="Idempotency-Key 必须为 1-128 字符")
    account_type = (billing_account_type or "").strip()
    if account_type not in {"user", "organization"}:
        raise HTTPException(status_code=422, detail="无效计费主体类型")
    account_id = str(billing_account_id or user_id)
    if not account_id:
        raise HTTPException(status_code=409, detail={"error": "billing_account_missing"})
    units = max(1, int(units))
    resolved_quota = int(quota_override) if quota_override is not None else None
    if not metering_enabled():
        return {
            "reservation_id": None,
            "idempotency_key": key,
            "feature": feature,
            "status": "disabled",
            "reserved_units": units,
            "created": True,
            "billing_account_type": account_type,
            "billing_account_id": account_id,
            "period_key": period_key or _month_key(),
        }
    if resolved_quota is None:
        raise HTTPException(
            status_code=409,
            detail={"error": "billing_entitlement_required"},
        )

    month_key = _month_key()
    resolved_period_key = period_key or month_key
    fingerprint = request_fingerprint or _request_fingerprint(meta)
    if len(fingerprint) != 64:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_request_fingerprint"},
        )
    existing = await _find_reservation(
        db,
        billing_account_type=account_type,
        billing_account_id=account_id,
        feature=feature,
        period_key=resolved_period_key,
        idempotency_key=key,
    )
    if existing and existing.request_fingerprint != fingerprint:
        raise HTTPException(
            status_code=409,
            detail={"error": "idempotency_conflict"},
        )
    if existing and existing.status != "released":
        return _reservation_payload(existing, created=False)

    lock_key = f"{account_type}:{account_id}:{feature}:{resolved_period_key}"
    local_lock = _sqlite_reservation_locks.setdefault(lock_key, asyncio.Lock())

    async def _reserve_locked() -> dict:
        if db.bind and db.bind.dialect.name == "postgresql":
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": lock_key},
            )
        duplicate = await _find_reservation(
            db,
            billing_account_type=account_type,
            billing_account_id=account_id,
            feature=feature,
            period_key=resolved_period_key,
            idempotency_key=key,
        )
        if duplicate and duplicate.request_fingerprint != fingerprint:
            await db.rollback()
            raise HTTPException(
                status_code=409,
                detail={"error": "idempotency_conflict"},
            )
        if duplicate and duplicate.status != "released":
            await db.commit()
            return _reservation_payload(duplicate, created=False)

        stale_before = datetime.now(timezone.utc) - timedelta(
            seconds=max(
                60,
                int(os.getenv("QUOTA_RESERVATION_TTL_SECONDS", "900")),
            )
        )
        await db.execute(
            update(UsageReservation)
            .where(
                UsageReservation.billing_account_type == account_type,
                UsageReservation.billing_account_id == account_id,
                UsageReservation.feature == feature,
                UsageReservation.period_key == resolved_period_key,
                UsageReservation.status == "reserved",
                UsageReservation.created_at < stale_before,
            )
            .values(status="released")
        )

        used = int(
            (
                await db.execute(
                    select(func.coalesce(func.sum(UsageEvent.units), 0)).where(
                        UsageEvent.billing_account_type == account_type,
                        UsageEvent.billing_account_id == account_id,
                        UsageEvent.feature == feature,
                        UsageEvent.period_key == resolved_period_key,
                    )
                )
            ).scalar()
            or 0
        )
        reserved = int(
            (
                await db.execute(
                    select(func.coalesce(func.sum(UsageReservation.reserved_units), 0)).where(
                        UsageReservation.billing_account_type == account_type,
                        UsageReservation.billing_account_id == account_id,
                        UsageReservation.feature == feature,
                        UsageReservation.period_key == resolved_period_key,
                        UsageReservation.status == "reserved",
                    )
                )
            ).scalar()
            or 0
        )
        quota = int(resolved_quota)
        if used + reserved + units > quota:
            await db.rollback()
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "quota_exceeded",
                    "feature": feature,
                    "used": used,
                    "reserved": reserved,
                    "quota": quota,
                },
            )

        if duplicate:
            previous_meta = dict(duplicate.meta or {})
            failure_reason = previous_meta.pop("failure_reason", None)
            failure_history = list(previous_meta.pop("attempt_failures", []))
            if failure_reason:
                failure_history.append(
                    {
                        "reason": failure_reason,
                        "released_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            duplicate.reserved_units = units
            duplicate.status = "reserved"
            duplicate.attempt = int(duplicate.attempt or 1) + 1
            duplicate.request_fingerprint = fingerprint
            duplicate.error_code = None
            duplicate.model_called = False
            duplicate.finalized_at = None
            duplicate.created_at = datetime.now(timezone.utc)
            duplicate.meta = {
                **previous_meta,
                **(meta or {}),
                "attempt_count": int(previous_meta.get("attempt_count") or 1) + 1,
                "attempt_failures": failure_history,
            }
            row = duplicate
        else:
            row = UsageReservation(
                id=str(uuid.uuid4()),
                user_id=user_id,
                billing_account_type=account_type,
                billing_account_id=account_id,
                feature=feature,
                month_key=month_key,
                period_key=resolved_period_key,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                attempt=1,
                reserved_units=units,
                status="reserved",
                meta={**(meta or {}), "attempt_count": 1},
            )
            db.add(row)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            duplicate = await _find_reservation(
                db,
                billing_account_type=account_type,
                billing_account_id=account_id,
                feature=feature,
                period_key=resolved_period_key,
                idempotency_key=key,
            )
            if duplicate:
                return _reservation_payload(duplicate, created=False)
            raise
        await db.refresh(row)
        return _reservation_payload(row, created=True)

    if db.bind and db.bind.dialect.name == "postgresql":
        return await _reserve_locked()
    async with local_lock:
        return await _reserve_locked()


async def finalize_quota(
    db: AsyncSession,
    reservation_id: Optional[str],
    *,
    succeeded: bool,
    failure_reason: Optional[str] = None,
    meta: Optional[dict] = None,
) -> dict:
    """幂等完成预占；成功只写一条 UsageEvent，失败释放容量。"""
    from .models_db import UsageEvent, UsageReservation

    if not reservation_id:
        return {"status": "disabled"}
    stmt = select(UsageReservation).where(UsageReservation.id == reservation_id).with_for_update()
    row = (await db.execute(stmt)).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="配额预占不存在")
    if row.status != "reserved":
        return _reservation_payload(row, created=False)

    combined_meta = {**(row.meta or {}), **(meta or {})}
    if succeeded:
        row.status = "succeeded"
        db.add(
            UsageEvent(
                user_id=row.user_id,
                billing_account_type=row.billing_account_type or "user",
                billing_account_id=row.billing_account_id or row.user_id,
                feature=row.feature,
                units=row.reserved_units,
                month_key=row.month_key,
                period_key=row.period_key or row.month_key,
                meta={**combined_meta, "reservation_id": str(row.id)},
            )
        )
    else:
        row.status = "released"
        combined_meta["failure_reason"] = failure_reason or "operation_failed"
        row.error_code = combined_meta["failure_reason"]
    row.model_called = bool(combined_meta.get("model_called"))
    row.finalized_at = datetime.now(timezone.utc)
    row.meta = combined_meta
    await db.commit()
    await db.refresh(row)
    return _reservation_payload(row, created=False)


async def get_usage_summary(db: AsyncSession, user_id: str) -> dict:
    from .models_db import UsageEvent, UsageReservation

    mk = _month_key()
    stmt = select(UsageEvent).where(
        UsageEvent.user_id == user_id,
        UsageEvent.month_key == mk,
    )
    result = await db.execute(stmt)
    events = result.scalars().all()
    by_feature: dict = {}
    for e in events:
        bucket = by_feature.setdefault(e.feature, {"used": 0})
        bucket["used"] += e.units or 1

    reservation_rows = (
        (
            await db.execute(
                select(UsageReservation).where(
                    UsageReservation.user_id == user_id,
                    UsageReservation.month_key == mk,
                )
            )
        )
        .scalars()
        .all()
    )
    reservation_status: dict[str, dict[str, int]] = {}
    for reservation in reservation_rows:
        status_bucket = reservation_status.setdefault(reservation.feature, {})
        status_bucket[reservation.status] = (
            status_bucket.get(reservation.status, 0) + reservation.reserved_units
        )

    return {
        "month": mk,
        "metering_enabled": metering_enabled(),
        "by_feature": by_feature,
        "reservation_status": reservation_status,
        "deprecated": True,
        "canonical_endpoint": "/billing/me",
    }
