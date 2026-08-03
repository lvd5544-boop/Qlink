from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select


pytestmark = pytest.mark.asyncio


async def test_candidate_billing_view_exposes_confirmed_entitlements_not_costs(
    client,
    auth_header,
    candidate_a,
    candidate_free_subscription,
):
    response = await client.get(
        "/billing/me",
        headers=auth_header(candidate_a),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["plan"]["code"] == "candidate-free-v1"
    assert payload["plan"]["currency"] == "CNY"
    assert payload["plan"]["price_minor_units"] == 0
    entitlements = {(item["feature"], item["period"]): item for item in payload["entitlements"]}
    assert entitlements[("resume_coach", "month")]["limit"] == 50
    assert entitlements[("evidence_regenerate", "month")]["limit"] == 50
    assert entitlements[("interview_session", "day")]["limit"] == 50
    assert entitlements[("interview_turn", "session")]["limit"] == 50
    plans = {plan["code"]: plan for plan in payload["available_plans"]}
    assert plans["candidate-pro-v1"]["price_minor_units"] == 2000
    assert payload["reset_timezone"] == "Asia/Shanghai"
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    for forbidden in ("token", "provider", "cost_microunits", "price_version"):
        assert forbidden not in serialized


async def test_organization_billing_view_shows_seats_shared_quota_and_pack(
    client,
    auth_header,
    employer_a,
    employer_organization_subscription,
):
    response = await client.get(
        "/billing/organization",
        headers=auth_header(employer_a),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["plan"]["code"] == "organization-seat-v1"
    assert payload["plan"]["price_minor_units"] == 30000
    assert payload["seats"] == {
        "quantity": 1,
        "occupied": 1,
        "remaining": 0,
    }
    audit = next(item for item in payload["entitlements"] if item["feature"] == "credibility_audit")
    assert audit["limit"] == 300
    assert payload["available_credit_packs"] == [
        {
            "code": "organization-audit-100-v1",
            "feature": "credibility_audit",
            "currency": "CNY",
            "price_minor_units": 10000,
            "grant_units": 100,
            "version": 1,
        }
    ]
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    for forbidden in ("token", "provider", "cost_microunits", "price_version"):
        assert forbidden not in serialized


async def test_candidate_usage_never_exposes_provider_or_estimated_cost(
    client, auth_header, db_session, candidate_a
):
    from app.models_db import UsageEvent

    db_session.add(
        UsageEvent(
            user_id=candidate_a.id,
            feature="resume_coach",
            units=1,
            month_key="2026-07",
            meta={
                "provider": "secret-provider",
                "model": "secret-model",
                "input_tokens": 999,
                "estimated_cost_usd": 12.345678,
            },
        )
    )
    await db_session.commit()

    response = await client.get("/usage/me", headers=auth_header(candidate_a))
    assert response.status_code == 200
    serialized = json.dumps(response.json(), ensure_ascii=False).lower()
    for forbidden in (
        "cost",
        "usd",
        "token",
        "provider",
        "secret-model",
        "secret-provider",
    ):
        assert forbidden not in serialized


async def test_only_admin_can_read_provider_token_costs(
    client,
    auth_header,
    db_session,
    candidate_a,
    employer_a,
    admin_user,
):
    from app.models_db import ProviderCostEvent

    event = ProviderCostEvent(
        user_id=candidate_a.id,
        feature="resume_coach",
        provider="deepseek",
        model="deepseek-chat",
        model_version="2026-07",
        prompt_version="resume-coach-v1",
        provider_request_id="provider-request-1",
        input_tokens=120,
        output_tokens=30,
        cache_hit_tokens=20,
        cache_miss_tokens=100,
        currency="CNY",
        cost_microunits=12345,
        cost_minor_units=1,
        price_version="deepseek-2026-07",
        provider_status="succeeded",
    )
    db_session.add(event)
    await db_session.commit()

    endpoint = "/admin/billing/provider-costs?page=1&page_size=20"
    for user in (candidate_a, employer_a):
        denied = await client.get(endpoint, headers=auth_header(user))
        assert denied.status_code == 403

    response = await client.get(endpoint, headers=auth_header(admin_user))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"]["total"] == 1
    assert payload["meta"]["page"] == 1
    assert payload["data"][0]["provider_request_id"] == "provider-request-1"
    assert payload["data"][0]["input_tokens"] == 120
    assert payload["data"][0]["output_tokens"] == 30
    assert payload["data"][0]["cost_microunits"] == 12345
    assert payload["data"][0]["currency"] == "CNY"


async def test_rule_only_faithful_rewrite_does_not_consume_ai_credit(
    client,
    auth_header,
    db_session,
    candidate_a,
    candidate_free_subscription,
    resume_a,
    monkeypatch,
):
    from app.models_db import UsageEvent, UsageReservation

    monkeypatch.setenv("METERING_ENABLED", "true")
    monkeypatch.setenv("EVIDENCE_FOLLOWUP_STRICT", "true")

    response = await client.post(
        f"/resumes/{resume_a.id}/evidence-followup/regenerate",
        headers={
            **auth_header(candidate_a),
            "Idempotency-Key": "rule-only-rewrite-1",
        },
        json={
            "entry_type": "work",
            "index": 0,
            "answers": [
                {
                    "id": "scope",
                    "question": "你负责什么？",
                    "answer": "负责订单模块开发",
                }
            ],
            "rewrite_mode": "conservative",
        },
    )
    assert response.status_code == 200, response.text
    assert "_metering" not in response.json()

    event_count = (
        await db_session.execute(select(func.count()).select_from(UsageEvent))
    ).scalar_one()
    reservation = (
        await db_session.execute(
            select(UsageReservation).where(
                UsageReservation.idempotency_key == "rule-only-rewrite-1"
            )
        )
    ).scalar_one()
    assert event_count == 0
    assert reservation.status == "released"
    assert reservation.meta["failure_reason"] == "no_model_call"


async def test_rejected_model_output_refunds_credit_but_keeps_token_cost(
    client,
    auth_header,
    db_session,
    candidate_a,
    candidate_free_subscription,
    resume_a,
    monkeypatch,
):
    from app import evidence_followup
    from app.models_db import ProviderCostEvent, UsageEvent, UsageReservation

    response_object = SimpleNamespace(
        id="provider-rejected-output-1",
        model="deepseek-chat-versioned",
        usage=SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=30,
            prompt_cache_hit_tokens=20,
            prompt_cache_miss_tokens=100,
        ),
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="主导阿里云订单平台并将业绩提升99%"))
        ],
    )
    monkeypatch.setattr(evidence_followup, "sync_chat_completion", lambda **_kwargs: response_object)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only")
    monkeypatch.setenv("AI_PRIMARY_API_KEY", "test-only")
    monkeypatch.setenv("EVIDENCE_FOLLOWUP_STRICT", "false")
    monkeypatch.setenv("METERING_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_INPUT_PRICE_CNY_PER_MILLION", "2")
    monkeypatch.setenv("DEEPSEEK_OUTPUT_PRICE_CNY_PER_MILLION", "4")
    monkeypatch.setenv("DEEPSEEK_CACHE_HIT_PRICE_CNY_PER_MILLION", "0.5")
    monkeypatch.setenv("DEEPSEEK_CACHE_MISS_PRICE_CNY_PER_MILLION", "2")
    monkeypatch.setenv("DEEPSEEK_PRICE_VERSION", "test-price-v1")

    response = await client.post(
        f"/resumes/{resume_a.id}/evidence-followup/regenerate",
        headers={
            **auth_header(candidate_a),
            "Idempotency-Key": "rejected-model-output-1",
        },
        json={
            "entry_type": "work",
            "index": 0,
            "answers": [
                {
                    "id": "scope",
                    "question": "你负责什么？",
                    "answer": "负责订单模块开发",
                }
            ],
            "rewrite_mode": "standard",
        },
    )
    assert response.status_code == 200, response.text
    assert "阿里云" not in response.json()["example_after"]

    usage_events = (await db_session.execute(select(UsageEvent))).scalars().all()
    reservation = (
        await db_session.execute(
            select(UsageReservation).where(
                UsageReservation.idempotency_key == "rejected-model-output-1"
            )
        )
    ).scalar_one()
    cost = (await db_session.execute(select(ProviderCostEvent))).scalar_one()
    assert usage_events == []
    assert reservation.status == "released"
    assert reservation.meta["failure_reason"] == "model_output_not_delivered"
    assert cost.provider_request_id == "provider-rejected-output-1"
    assert cost.input_tokens == 120
    assert cost.output_tokens == 30
    assert cost.cache_hit_tokens == 20
    assert cost.cache_miss_tokens == 100
    assert cost.cost_microunits == 330
    assert cost.price_version == "test-price-v1"


async def test_both_coach_entrypoints_release_rule_only_results(
    client,
    auth_header,
    db_session,
    candidate_a,
    candidate_free_subscription,
    resume_a,
    monkeypatch,
):
    from app import resume_coach_service
    from app.models_db import UsageEvent, UsageReservation

    async def rule_only_coach(*_args, **_kwargs):
        return {
            "coach": {"suggestions": []},
            "_metering": {
                "model_called": False,
                "provider_status": None,
                "provider_usage": None,
                "model_output_used": False,
            },
        }

    monkeypatch.setattr(
        resume_coach_service,
        "generate_resume_coach",
        rule_only_coach,
    )
    monkeypatch.setenv("METERING_ENABLED", "true")

    embedded = await client.post(
        f"/resumes/{resume_a.id}/coach",
        headers={
            **auth_header(candidate_a),
            "Idempotency-Key": "embedded-coach-rule-1",
        },
        json={"company_id": "company-1", "role_family": "engineering"},
    )
    analytics = await client.post(
        "/analytics/resume-coach",
        headers={
            **auth_header(candidate_a),
            "Idempotency-Key": "analytics-coach-rule-1",
        },
        json={
            "resume_id": str(resume_a.id),
            "company_id": "company-1",
            "role_family": "engineering",
        },
    )
    assert embedded.status_code == 200, embedded.text
    assert analytics.status_code == 200, analytics.text
    assert "_metering" not in embedded.json()
    assert "_metering" not in analytics.json()

    events = (await db_session.execute(select(UsageEvent))).scalars().all()
    reservations = (
        (
            await db_session.execute(
                select(UsageReservation).order_by(UsageReservation.idempotency_key)
            )
        )
        .scalars()
        .all()
    )
    assert events == []
    assert [row.idempotency_key for row in reservations] == [
        "analytics-coach-rule-1",
        "embedded-coach-rule-1",
    ]
    assert all(row.status == "released" for row in reservations)


async def test_rule_only_credibility_audit_does_not_consume_shared_credit(
    client,
    auth_header,
    db_session,
    employer_a,
    employer_organization_subscription,
    application_a,
    monkeypatch,
):
    from app import application_routes
    from app.models_db import CredibilityAuditRecord, UsageEvent, UsageReservation

    monkeypatch.setenv("METERING_ENABLED", "true")
    monkeypatch.setattr(
        application_routes,
        "build_credibility_report",
        lambda *_args, **_kwargs: {
            "overall_status": "clear",
            "risk_score": 0,
            "findings": [],
            "_metering": {
                "model_called": False,
                "provider_status": None,
                "provider_usage": None,
                "model_output_used": False,
            },
        },
    )

    response = await client.get(
        f"/applications/{application_a.id}/credibility-audit",
        headers={
            **auth_header(employer_a),
            "Idempotency-Key": "rule-only-audit-1",
        },
    )
    assert response.status_code == 200, response.text
    assert "_metering" not in json.dumps(response.json())

    events = (await db_session.execute(select(UsageEvent))).scalars().all()
    reservation = (
        await db_session.execute(
            select(UsageReservation).where(UsageReservation.idempotency_key == "rule-only-audit-1")
        )
    ).scalar_one()
    record = (
        await db_session.execute(
            select(CredibilityAuditRecord).where(
                CredibilityAuditRecord.id == response.json()["audit_record_id"]
            )
        )
    ).scalar_one()
    assert events == []
    assert reservation.status == "released"
    assert "_metering" not in record.report
