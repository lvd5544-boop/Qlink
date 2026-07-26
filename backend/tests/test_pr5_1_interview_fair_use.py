from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, update


pytestmark = pytest.mark.asyncio


async def _set_limit(db_session, *, feature: str, limit: int) -> None:
    from app.models_db import PlanEntitlement

    await db_session.execute(
        update(PlanEntitlement)
        .where(
            PlanEntitlement.plan_code == "candidate-free-v1",
            PlanEntitlement.feature == feature,
        )
        .values(limit_units=limit)
    )
    await db_session.commit()


async def test_free_interview_daily_sessions_are_limited_without_paid_credits(
    db_session,
    candidate_a,
    candidate_free_subscription,
):
    from app.interview_fair_use import (
        close_interview_session,
        start_interview_session,
    )
    from app.models_db import UsageEvent, UsageReservation

    await _set_limit(db_session, feature="interview_session", limit=2)
    for _ in range(2):
        fair_use = await start_interview_session(
            db_session,
            actor=candidate_a,
            mode="profile",
        )
        await close_interview_session(db_session, fair_use)

    with pytest.raises(HTTPException) as exc_info:
        await start_interview_session(
            db_session,
            actor=candidate_a,
            mode="profile",
        )
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == {
        "error": "fair_use_exceeded",
        "feature": "ai_interview",
        "limit_type": "daily_sessions",
        "limit": 2,
        "used": 2,
    }
    assert (
        await db_session.execute(select(func.count()).select_from(UsageEvent))
    ).scalar_one() == 0
    assert (
        await db_session.execute(select(func.count()).select_from(UsageReservation))
    ).scalar_one() == 0


async def test_free_interview_turn_limit_and_single_active_connection(
    db_session,
    candidate_a,
    candidate_free_subscription,
):
    from app.interview_fair_use import (
        close_interview_session,
        consume_interview_turn,
        start_interview_session,
    )

    await _set_limit(db_session, feature="interview_turn", limit=2)
    fair_use = await start_interview_session(
        db_session,
        actor=candidate_a,
        mode="claim_followup",
    )
    with pytest.raises(HTTPException) as active_exc:
        await start_interview_session(
            db_session,
            actor=candidate_a,
            mode="profile",
        )
    assert active_exc.value.status_code == 429
    assert active_exc.value.detail["limit_type"] == "active_connections"

    assert await consume_interview_turn(db_session, fair_use) == 1
    assert await consume_interview_turn(db_session, fair_use) == 2
    with pytest.raises(HTTPException) as turn_exc:
        await consume_interview_turn(db_session, fair_use)
    assert turn_exc.value.status_code == 429
    assert turn_exc.value.detail["limit_type"] == "session_turns"
    await close_interview_session(db_session, fair_use)


async def test_interview_uses_china_local_day():
    from app.interview_fair_use import local_day_key

    at_boundary = datetime(2026, 7, 31, 16, 30, tzinfo=timezone.utc)
    assert local_day_key(at_boundary) == "2026-08-01"


async def test_interview_model_cost_is_admin_audit_only(
    client,
    auth_header,
    db_session,
    candidate_a,
    admin_user,
    monkeypatch,
):
    from app.interview import _record_interview_cost
    from app.models_db import ProviderCostEvent

    monkeypatch.setenv("DEEPSEEK_INPUT_PRICE_CNY_PER_MILLION", "2")
    monkeypatch.setenv("DEEPSEEK_OUTPUT_PRICE_CNY_PER_MILLION", "4")
    monkeypatch.setenv("DEEPSEEK_PRICE_VERSION", "interview-price-v1")
    response = SimpleNamespace(
        id="interview-provider-request-1",
        model="deepseek-chat-versioned",
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=20,
        ),
    )
    await _record_interview_cost(
        db_session,
        user_id=str(candidate_a.id),
        response=response,
        model="deepseek-chat",
        prompt_version="interview-profile-turn-v1",
        provider_status="succeeded",
    )
    event = (await db_session.execute(select(ProviderCostEvent))).scalar_one()
    assert event.feature == "interview_turn"
    assert event.input_tokens == 100
    assert event.output_tokens == 20
    assert event.cost_microunits == 280

    denied = await client.get(
        "/admin/billing/provider-costs",
        headers=auth_header(candidate_a),
    )
    allowed = await client.get(
        "/admin/billing/provider-costs",
        headers=auth_header(admin_user),
    )
    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["data"][0]["feature"] == "interview_turn"
