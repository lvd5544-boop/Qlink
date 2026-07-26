from __future__ import annotations

import pytest
from sqlalchemy import update


pytestmark = pytest.mark.asyncio


def _assert_error_envelope(response, *, code: str) -> None:
    payload = response.json()
    assert payload["error"]["code"] == code
    assert payload["error"]["request_id"] == response.headers["X-Request-ID"]
    assert isinstance(payload["error"]["message"], str)
    assert isinstance(payload["error"]["fields"], dict)
    # Temporary compatibility field exists during PR5.5 only.
    assert "detail" in payload


async def test_http_errors_have_stable_code_and_request_id(
    client,
    auth_header,
    candidate_a,
):
    response = await client.get(
        "/resume/missing-resume",
        headers={
            **auth_header(candidate_a),
            "X-Request-ID": "contract-request-1",
        },
    )
    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "contract-request-1"
    _assert_error_envelope(response, code="resource.not_found")


async def test_validation_errors_use_field_map(client):
    response = await client.post(
        "/auth/register",
        json={"email": "missing-password@test.local"},
    )
    assert response.status_code == 422
    _assert_error_envelope(response, code="request.validation_failed")
    assert "body.password" in response.json()["error"]["fields"]


async def test_free_product_quota_exhaustion_uses_429_not_payment_required(
    client,
    auth_header,
    db_session,
    candidate_a,
    candidate_free_subscription,
    resume_a,
    monkeypatch,
):
    from app.models_db import PlanEntitlement

    await db_session.execute(
        update(PlanEntitlement)
        .where(
            PlanEntitlement.plan_code == "candidate-free-v1",
            PlanEntitlement.feature == "resume_coach",
        )
        .values(limit_units=0)
    )
    await db_session.commit()
    monkeypatch.setenv("METERING_ENABLED", "true")

    response = await client.post(
        f"/resumes/{resume_a.id}/coach",
        headers={
            **auth_header(candidate_a),
            "Idempotency-Key": "quota-exhausted-contract",
        },
        json={"company_id": "company-1"},
    )
    assert response.status_code == 429
    _assert_error_envelope(response, code="billing.quota_exceeded")
    assert response.json()["error"]["fields"]["quota"] == 0
