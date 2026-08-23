from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import pytest
from sqlalchemy import select

from app import auth_routes
from app.models_db import PasswordResetToken


@pytest.fixture(autouse=True)
def reset_recovery_state(monkeypatch):
    auth_routes._password_reset_attempts.clear()
    monkeypatch.setenv("PUBLIC_ORIGIN", "http://test")
    monkeypatch.setenv("PASSWORD_RESET_LIMIT", "100")
    monkeypatch.setattr(auth_routes, "smtp_configured", lambda: True)


@pytest.mark.asyncio
async def test_password_reset_is_generic_hashed_single_use_and_revokes_sessions(
    client, candidate_a, db_session, monkeypatch
):
    sent = []

    async def capture_email(to, subject, html_content):
        sent.append((to, subject, html_content))

    monkeypatch.setattr(auth_routes, "send_email", capture_email)
    old_login = await client.post(
        "/auth/login",
        json={"email": candidate_a.email, "password": "test-pass-123"},
    )
    assert old_login.status_code == 200
    old_header = {"Authorization": f"Bearer {old_login.json()['access_token']}"}

    response = await client.post("/auth/password-reset/request", json={"email": candidate_a.email})
    unknown = await client.post(
        "/auth/password-reset/request", json={"email": "missing@test.local"}
    )
    assert response.status_code == unknown.status_code == 202
    assert response.json() == unknown.json() == {"status": "accepted"}
    assert len(sent) == 1

    match = re.search(r"token=([^\"<]+)", sent[0][2])
    assert match
    raw_token = unquote(match.group(1))
    row = (await db_session.execute(select(PasswordResetToken))).scalars().one()
    assert row.token_hash == hashlib.sha256(raw_token.encode()).hexdigest()
    assert raw_token not in row.token_hash

    changed = await client.post(
        "/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "FreshSecure9Z"},
    )
    assert changed.status_code == 200
    replay = await client.post(
        "/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "AnotherFresh8Y"},
    )
    assert replay.status_code == 400
    assert (await client.get("/pilot/me", headers=old_header)).status_code == 401
    assert (
        await client.post(
            "/auth/login",
            json={"email": candidate_a.email, "password": "test-pass-123"},
        )
    ).status_code == 401
    assert (
        await client.post(
            "/auth/login",
            json={"email": candidate_a.email, "password": "FreshSecure9Z"},
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_expired_reset_token_is_rejected(client, candidate_a, db_session, monkeypatch):
    token = "x" * 43
    db_session.add(
        PasswordResetToken(
            user_id=candidate_a.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    )
    await db_session.commit()
    response = await client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "new_password": "FreshSecure9Z"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_password_change_revokes_every_existing_token(client, candidate_a):
    payload = {"email": candidate_a.email, "password": "test-pass-123"}
    login_a = await client.post("/auth/login", json=payload)
    login_b = await client.post("/auth/login", json=payload)
    headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    changed = await client.post(
        "/auth/password/change",
        headers=headers_a,
        json={
            "current_password": "test-pass-123",
            "new_password": "FreshSecure9Z",
        },
    )
    assert changed.status_code == 200
    assert (await client.get("/pilot/me", headers=headers_a)).status_code == 401
    assert (await client.get("/pilot/me", headers=headers_b)).status_code == 401


@pytest.mark.asyncio
async def test_reset_email_failure_consumes_token_and_keeps_generic_response(
    client, candidate_a, db_session, monkeypatch
):
    async def fail_email(*_args):
        raise RuntimeError("mail unavailable")

    monkeypatch.setattr(auth_routes, "send_email", fail_email)
    response = await client.post("/auth/password-reset/request", json={"email": candidate_a.email})
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    row = (await db_session.execute(select(PasswordResetToken))).scalars().one()
    await db_session.refresh(row)
    assert row.used_at is not None


@pytest.mark.asyncio
async def test_reset_without_smtp_does_not_persist_token(
    client, candidate_a, db_session, monkeypatch
):
    monkeypatch.setattr(auth_routes, "smtp_configured", lambda: False)
    response = await client.post("/auth/password-reset/request", json={"email": candidate_a.email})
    assert response.status_code == 202
    rows = (await db_session.execute(select(PasswordResetToken))).scalars().all()
    assert rows == []
