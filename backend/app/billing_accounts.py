"""Resolve candidate or organization entitlements into one billing account."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models_db import (
    Organization,
    OrganizationMembership,
    OrganizationSubscription,
    Plan,
    PlanEntitlement,
    User,
    UserSubscription,
)
from .usage_metering import (
    _month_key,
    _request_fingerprint,
    metering_enabled,
    reserve_quota,
)


@dataclass(frozen=True)
class BillingEntitlement:
    account_type: str
    account_id: str
    plan_code: str
    feature: str
    limit_units: Optional[int]
    period: str
    meter_type: str
    period_end: datetime


def _billing_error(code: str, *, status_code: int = 409) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": code})


async def _active_entitlement(
    db: AsyncSession,
    *,
    plan_code: str,
    feature: str,
) -> PlanEntitlement:
    entitlement = (
        (
            await db.execute(
                select(PlanEntitlement).where(
                    PlanEntitlement.plan_code == plan_code,
                    PlanEntitlement.feature == feature,
                )
            )
        )
        .scalars()
        .first()
    )
    if not entitlement:
        raise _billing_error("feature_not_in_plan", status_code=402)
    return entitlement


async def resolve_billing_entitlement(
    db: AsyncSession,
    *,
    actor: User,
    feature: str,
    now: Optional[datetime] = None,
) -> BillingEntitlement:
    current_time = now or datetime.now(timezone.utc)

    if actor.role == "candidate":
        subscription = (
            (
                await db.execute(
                    select(UserSubscription)
                    .join(Plan, Plan.code == UserSubscription.plan_code)
                    .where(
                        UserSubscription.user_id == str(actor.id),
                        UserSubscription.status.in_(("active", "trialing")),
                        UserSubscription.period_start <= current_time,
                        UserSubscription.period_end > current_time,
                        Plan.active.is_(True),
                        Plan.audience == "candidate",
                    )
                    .order_by(
                        UserSubscription.period_start.desc(),
                        UserSubscription.created_at.desc(),
                    )
                )
            )
            .scalars()
            .first()
        )
        if not subscription:
            raise _billing_error("subscription_inactive", status_code=402)
        entitlement = await _active_entitlement(
            db,
            plan_code=subscription.plan_code,
            feature=feature,
        )
        return BillingEntitlement(
            account_type="user",
            account_id=str(actor.id),
            plan_code=subscription.plan_code,
            feature=feature,
            limit_units=entitlement.limit_units,
            period=entitlement.period,
            meter_type=entitlement.meter_type,
            period_end=subscription.period_end,
        )

    if actor.role != "employer":
        raise _billing_error("billing_account_missing")

    memberships = (
        (
            await db.execute(
                select(OrganizationMembership)
                .join(
                    Organization,
                    Organization.id == OrganizationMembership.organization_id,
                )
                .where(
                    OrganizationMembership.user_id == str(actor.id),
                    OrganizationMembership.status == "active",
                    Organization.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    if not memberships:
        raise _billing_error("billing_account_missing")
    if len(memberships) != 1:
        raise _billing_error("billing_account_ambiguous")
    membership = memberships[0]

    subscription = (
        (
            await db.execute(
                select(OrganizationSubscription)
                .join(Plan, Plan.code == OrganizationSubscription.plan_code)
                .where(
                    OrganizationSubscription.organization_id == membership.organization_id,
                    OrganizationSubscription.status.in_(("active", "trialing")),
                    OrganizationSubscription.period_start <= current_time,
                    OrganizationSubscription.period_end > current_time,
                    Plan.active.is_(True),
                    Plan.audience == "organization",
                )
                .order_by(
                    OrganizationSubscription.period_start.desc(),
                    OrganizationSubscription.created_at.desc(),
                )
            )
        )
        .scalars()
        .first()
    )
    if not subscription:
        raise _billing_error("subscription_inactive", status_code=402)

    active_seats = int(
        (
            await db.execute(
                select(func.count())
                .select_from(OrganizationMembership)
                .where(
                    OrganizationMembership.organization_id == membership.organization_id,
                    OrganizationMembership.status.in_(("active", "invited")),
                )
            )
        ).scalar()
        or 0
    )
    if active_seats > subscription.seat_quantity:
        raise _billing_error("seat_limit_exceeded", status_code=402)

    entitlement = await _active_entitlement(
        db,
        plan_code=subscription.plan_code,
        feature=feature,
    )
    return BillingEntitlement(
        account_type="organization",
        account_id=str(membership.organization_id),
        plan_code=subscription.plan_code,
        feature=feature,
        limit_units=entitlement.limit_units,
        period=entitlement.period,
        meter_type=entitlement.meter_type,
        period_end=subscription.period_end,
    )


async def reserve_feature_entitlement(
    db: AsyncSession,
    *,
    actor: User,
    feature: str,
    idempotency_key: str,
    request_payload: dict,
    reservation_meta: Optional[dict] = None,
) -> dict:
    if not metering_enabled():
        return {
            "reservation_id": None,
            "idempotency_key": idempotency_key,
            "feature": feature,
            "status": "disabled",
            "reserved_units": 0,
            "created": True,
            "billing_account_type": ("organization" if actor.role == "employer" else "user"),
            # Metering-disabled compatibility mode has no authoritative
            # organization lookup. Never forge an organization FK from a
            # recruiter user id; provider costs may legitimately be unscoped.
            "billing_account_id": (None if actor.role == "employer" else str(actor.id)),
            "period_key": _month_key(),
        }
    entitlement = await resolve_billing_entitlement(
        db,
        actor=actor,
        feature=feature,
    )
    if entitlement.meter_type == "unmetered":
        return {
            "reservation_id": None,
            "idempotency_key": idempotency_key,
            "feature": feature,
            "status": "unmetered",
            "reserved_units": 0,
            "created": True,
            "billing_account_type": entitlement.account_type,
            "billing_account_id": entitlement.account_id,
        }
    if entitlement.limit_units is None:
        raise _billing_error("entitlement_limit_missing")

    return await reserve_quota(
        db,
        user_id=str(actor.id),
        feature=feature,
        idempotency_key=idempotency_key,
        units=1,
        meta={
            "plan_code": entitlement.plan_code,
            **(reservation_meta or {}),
        },
        billing_account_type=entitlement.account_type,
        billing_account_id=entitlement.account_id,
        period_key=_month_key(),
        quota_override=entitlement.limit_units,
        request_fingerprint=_request_fingerprint(request_payload),
    )
