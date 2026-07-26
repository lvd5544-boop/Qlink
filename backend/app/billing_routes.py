"""Billing visibility endpoints.

User-facing endpoints expose product entitlements only. Provider token and cost
fields are deliberately isolated behind the admin role.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .database import get_db
from .models_db import (
    CreditPackProduct,
    InterviewUsageSession,
    Organization,
    OrganizationMembership,
    OrganizationSubscription,
    Plan,
    PlanEntitlement,
    ProviderCostEvent,
    UsageEvent,
    UsageReservation,
    User,
    UserSubscription,
)
from .security import require_admin
from .usage_metering import _month_key


router = APIRouter(tags=["billing"])


def _local_day_key(now: Optional[datetime] = None) -> str:
    timezone_name = os.getenv("BILLING_TIMEZONE", "Asia/Shanghai")
    try:
        billing_timezone = ZoneInfo(timezone_name)
    except Exception as exc:
        raise RuntimeError(f"无效 BILLING_TIMEZONE: {timezone_name}") from exc
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(billing_timezone).strftime("%Y-%m-%d")


async def _usage_for_entitlement(
    db: AsyncSession,
    *,
    account_type: str,
    account_id: str,
    user_id: str,
    entitlement: PlanEntitlement,
) -> tuple[Optional[int], Optional[int], str]:
    if entitlement.period == "month":
        period_key = _month_key()
        used = int(
            (
                await db.execute(
                    select(func.coalesce(func.sum(UsageEvent.units), 0)).where(
                        UsageEvent.billing_account_type == account_type,
                        UsageEvent.billing_account_id == account_id,
                        UsageEvent.feature == entitlement.feature,
                        UsageEvent.period_key == period_key,
                    )
                )
            ).scalar()
            or 0
        )
        reserved = int(
            (
                await db.execute(
                    select(
                        func.coalesce(
                            func.sum(UsageReservation.reserved_units),
                            0,
                        )
                    ).where(
                        UsageReservation.billing_account_type == account_type,
                        UsageReservation.billing_account_id == account_id,
                        UsageReservation.feature == entitlement.feature,
                        UsageReservation.period_key == period_key,
                        UsageReservation.status == "reserved",
                    )
                )
            ).scalar()
            or 0
        )
        return used, reserved, period_key

    if entitlement.feature == "interview_session" and entitlement.period == "day":
        period_key = _local_day_key()
        used = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(InterviewUsageSession)
                    .where(
                        InterviewUsageSession.user_id == user_id,
                        InterviewUsageSession.local_day == period_key,
                    )
                )
            ).scalar()
            or 0
        )
        return used, 0, period_key

    # Per-session limits have no aggregate "used" value until a session is active.
    return None, None, "per_session"


async def _serialize_entitlements(
    db: AsyncSession,
    *,
    plan_code: str,
    account_type: str,
    account_id: str,
    user_id: str,
) -> list[dict]:
    entitlements = (
        (
            await db.execute(
                select(PlanEntitlement)
                .where(PlanEntitlement.plan_code == plan_code)
                .order_by(PlanEntitlement.feature, PlanEntitlement.period)
            )
        )
        .scalars()
        .all()
    )
    payload = []
    for entitlement in entitlements:
        used, reserved, period_key = await _usage_for_entitlement(
            db,
            account_type=account_type,
            account_id=account_id,
            user_id=user_id,
            entitlement=entitlement,
        )
        limit_units = entitlement.limit_units
        remaining = (
            None
            if limit_units is None or used is None
            else max(0, int(limit_units) - used - int(reserved or 0))
        )
        payload.append(
            {
                "feature": entitlement.feature,
                "period": entitlement.period,
                "meter_type": entitlement.meter_type,
                "limit": limit_units,
                "used": used,
                "reserved": reserved,
                "remaining": remaining,
                "period_key": period_key,
            }
        )
    return payload


def _plan_payload(plan: Plan) -> dict:
    return {
        "code": plan.code,
        "name": plan.name,
        "audience": plan.audience,
        "currency": plan.currency,
        "price_minor_units": plan.price_minor_units,
        "billing_period": plan.billing_period,
        "version": plan.version,
    }


@router.get("/billing/me")
async def get_my_billing(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "candidate":
        raise HTTPException(
            status_code=403,
            detail={"error": "candidate_billing_only"},
        )
    now = datetime.now(timezone.utc)
    row = (
        await db.execute(
            select(UserSubscription, Plan)
            .join(Plan, Plan.code == UserSubscription.plan_code)
            .where(
                UserSubscription.user_id == str(current_user.id),
                UserSubscription.status.in_(("active", "trialing")),
                UserSubscription.period_start <= now,
                UserSubscription.period_end > now,
                Plan.active.is_(True),
                Plan.audience == "candidate",
            )
            .order_by(UserSubscription.period_start.desc())
        )
    ).first()
    if not row:
        raise HTTPException(
            status_code=402,
            detail={"error": "subscription_inactive"},
        )
    subscription, plan = row
    available_plans = (
        (
            await db.execute(
                select(Plan)
                .where(
                    Plan.audience == "candidate",
                    Plan.active.is_(True),
                )
                .order_by(Plan.price_minor_units)
            )
        )
        .scalars()
        .all()
    )
    return {
        "billing_account": {
            "type": "user",
            "id": str(current_user.id),
        },
        "plan": _plan_payload(plan),
        "subscription": {
            "status": subscription.status,
            "period_start": subscription.period_start.isoformat(),
            "period_end": subscription.period_end.isoformat(),
            "cancel_at_period_end": subscription.cancel_at_period_end,
        },
        "entitlements": await _serialize_entitlements(
            db,
            plan_code=plan.code,
            account_type="user",
            account_id=str(current_user.id),
            user_id=str(current_user.id),
        ),
        "available_plans": [_plan_payload(candidate_plan) for candidate_plan in available_plans],
        "reset_timezone": os.getenv("BILLING_TIMEZONE", "Asia/Shanghai"),
    }


@router.get("/billing/organization")
async def get_organization_billing(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "employer":
        raise HTTPException(
            status_code=403,
            detail={"error": "organization_billing_only"},
        )
    memberships = (
        await db.execute(
            select(OrganizationMembership, Organization)
            .join(
                Organization,
                Organization.id == OrganizationMembership.organization_id,
            )
            .where(
                OrganizationMembership.user_id == str(current_user.id),
                OrganizationMembership.status == "active",
                Organization.status == "active",
            )
        )
    ).all()
    if len(memberships) != 1:
        raise HTTPException(
            status_code=409,
            detail={
                "error": (
                    "billing_account_missing" if not memberships else "billing_account_ambiguous"
                )
            },
        )
    membership, organization = memberships[0]
    if membership.role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=403,
            detail={"error": "organization_billing_admin_required"},
        )

    now = datetime.now(timezone.utc)
    row = (
        await db.execute(
            select(OrganizationSubscription, Plan)
            .join(Plan, Plan.code == OrganizationSubscription.plan_code)
            .where(
                OrganizationSubscription.organization_id == str(organization.id),
                OrganizationSubscription.status.in_(("active", "trialing")),
                OrganizationSubscription.period_start <= now,
                OrganizationSubscription.period_end > now,
                Plan.active.is_(True),
                Plan.audience == "organization",
            )
            .order_by(OrganizationSubscription.period_start.desc())
        )
    ).first()
    if not row:
        raise HTTPException(
            status_code=402,
            detail={"error": "subscription_inactive"},
        )
    subscription, plan = row
    active_seats = int(
        (
            await db.execute(
                select(func.count())
                .select_from(OrganizationMembership)
                .where(
                    OrganizationMembership.organization_id == str(organization.id),
                    OrganizationMembership.status.in_(("active", "invited")),
                )
            )
        ).scalar()
        or 0
    )
    packs = (
        (
            await db.execute(
                select(CreditPackProduct)
                .where(
                    CreditPackProduct.audience == "organization",
                    CreditPackProduct.active.is_(True),
                )
                .order_by(CreditPackProduct.price_minor_units)
            )
        )
        .scalars()
        .all()
    )
    return {
        "billing_account": {
            "type": "organization",
            "id": str(organization.id),
            "name": organization.name,
        },
        "plan": _plan_payload(plan),
        "subscription": {
            "status": subscription.status,
            "period_start": subscription.period_start.isoformat(),
            "period_end": subscription.period_end.isoformat(),
            "cancel_at_period_end": subscription.cancel_at_period_end,
        },
        "seats": {
            "quantity": subscription.seat_quantity,
            "occupied": active_seats,
            "remaining": max(0, subscription.seat_quantity - active_seats),
        },
        "entitlements": await _serialize_entitlements(
            db,
            plan_code=plan.code,
            account_type="organization",
            account_id=str(organization.id),
            user_id=str(current_user.id),
        ),
        "available_credit_packs": [
            {
                "code": pack.code,
                "feature": pack.feature,
                "currency": pack.currency,
                "price_minor_units": pack.price_minor_units,
                "grant_units": pack.grant_units,
                "version": pack.version,
            }
            for pack in packs
        ],
        "reset_timezone": os.getenv("BILLING_TIMEZONE", "Asia/Shanghai"),
    }


@router.get("/admin/billing/provider-costs")
async def list_provider_costs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    provider: Optional[str] = None,
    model: Optional[str] = None,
    feature: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if provider:
        filters.append(ProviderCostEvent.provider == provider)
    if model:
        filters.append(ProviderCostEvent.model == model)
    if feature:
        filters.append(ProviderCostEvent.feature == feature)
    if status:
        filters.append(ProviderCostEvent.provider_status == status)
    if date_from:
        filters.append(ProviderCostEvent.created_at >= date_from)
    if date_to:
        filters.append(ProviderCostEvent.created_at < date_to)

    total = int(
        (
            await db.execute(select(func.count()).select_from(ProviderCostEvent).where(*filters))
        ).scalar()
        or 0
    )
    rows = (
        (
            await db.execute(
                select(ProviderCostEvent)
                .where(*filters)
                .order_by(
                    ProviderCostEvent.created_at.desc(),
                    ProviderCostEvent.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return {
        "data": [
            {
                "id": str(row.id),
                "reservation_id": (str(row.reservation_id) if row.reservation_id else None),
                "user_id": str(row.user_id) if row.user_id else None,
                "organization_id": (str(row.organization_id) if row.organization_id else None),
                "feature": row.feature,
                "provider": row.provider,
                "model": row.model,
                "model_version": row.model_version,
                "prompt_version": row.prompt_version,
                "provider_request_id": row.provider_request_id,
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "cache_hit_tokens": row.cache_hit_tokens,
                "cache_miss_tokens": row.cache_miss_tokens,
                "currency": row.currency,
                "cost_microunits": row.cost_microunits,
                "cost_minor_units": row.cost_minor_units,
                "price_version": row.price_version,
                "provider_status": row.provider_status,
                "created_at": (row.created_at.isoformat() if row.created_at else None),
            }
            for row in rows
        ],
        "meta": {
            "page": page,
            "page_size": page_size,
            "total": total,
        },
    }
