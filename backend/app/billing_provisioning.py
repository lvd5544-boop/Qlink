"""Provision the default billing identity for newly registered users."""

from __future__ import annotations

from datetime import datetime, timezone
import os
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from .models_db import (
    Organization,
    OrganizationMembership,
    OrganizationSubscription,
    Plan,
    User,
    UserSubscription,
)


def current_billing_month_bounds(
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    timezone_name = os.getenv("BILLING_TIMEZONE", "Asia/Shanghai")
    try:
        billing_timezone = ZoneInfo(timezone_name)
    except Exception as exc:
        raise RuntimeError(f"无效 BILLING_TIMEZONE: {timezone_name}") from exc
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local = current.astimezone(billing_timezone)
    start_local = local.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    if start_local.month == 12:
        end_local = start_local.replace(
            year=start_local.year + 1,
            month=1,
        )
    else:
        end_local = start_local.replace(month=start_local.month + 1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


async def _require_plan(db: AsyncSession, code: str) -> Plan:
    plan = await db.get(Plan, code)
    if not plan or not plan.active:
        raise RuntimeError(f"计费目录缺少有效套餐 {code}；请先执行 PR5.1 pricing migration")
    return plan


async def provision_new_user_billing(
    db: AsyncSession,
    *,
    user: User,
) -> None:
    period_start, period_end = current_billing_month_bounds()
    if user.role == "candidate":
        await _require_plan(db, "candidate-free-v1")
        db.add(
            UserSubscription(
                user_id=str(user.id),
                plan_code="candidate-free-v1",
                status="active",
                period_start=period_start,
                period_end=period_end,
                cancel_at_period_end=False,
                source="manual",
            )
        )
        return

    if user.role == "employer":
        await _require_plan(db, "organization-seat-v1")
        organization = Organization(
            id=str(uuid.uuid4()),
            name=user.email or f"Employer {str(user.id)[:8]}",
            status="active",
        )
        db.add(organization)
        await db.flush()
        db.add_all(
            [
                OrganizationMembership(
                    organization_id=str(organization.id),
                    user_id=str(user.id),
                    role="owner",
                    status="active",
                ),
                OrganizationSubscription(
                    organization_id=str(organization.id),
                    plan_code="organization-seat-v1",
                    seat_quantity=1,
                    status="trialing",
                    period_start=period_start,
                    period_end=period_end,
                    cancel_at_period_end=False,
                    source="pilot",
                ),
            ]
        )
