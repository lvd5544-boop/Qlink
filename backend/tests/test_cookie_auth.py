from __future__ import annotations

import pytest

from app.auth import AUTH_COOKIE_NAME, CSRF_COOKIE_NAME


@pytest.mark.asyncio
async def test_browser_login_uses_httponly_cookie_and_csrf_for_writes(client, candidate_a):
    login = await client.post(
        "/auth/login",
        json={"email": candidate_a.email, "password": "test-pass-123"},
    )
    assert login.status_code == 200
    set_cookie = login.headers.get_list("set-cookie")
    session_cookie = next(value for value in set_cookie if value.startswith(AUTH_COOKIE_NAME))
    csrf_cookie = next(value for value in set_cookie if value.startswith(CSRF_COOKIE_NAME))
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "HttpOnly" not in csrf_cookie

    session = await client.get("/auth/session")
    assert session.status_code == 200
    assert session.json() == {
        "authenticated": True,
        "role": "candidate",
        "user_id": str(candidate_a.id),
    }

    denied = await client.post(
        "/auth/password/change",
        json={
            "current_password": "test-pass-123",
            "new_password": "CookieSecure9Z",
        },
    )
    assert denied.status_code == 403
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    allowed = await client.post(
        "/auth/password/change",
        headers={"X-CSRF-Token": csrf},
        json={
            "current_password": "test-pass-123",
            "new_password": "CookieSecure9Z",
        },
    )
    assert allowed.status_code == 200
    assert AUTH_COOKIE_NAME not in client.cookies


@pytest.mark.asyncio
async def test_bearer_clients_remain_supported_without_csrf(client, candidate_a):
    login = await client.post(
        "/auth/login",
        json={"email": candidate_a.email, "password": "test-pass-123"},
    )
    token = login.json()["access_token"]
    response = await client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_production_cookie_is_secure(client, candidate_a, monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("AUTH_STATE_BACKEND", "local")
    monkeypatch.delenv("AUTH_COOKIE_SECURE", raising=False)
    response = await client.post(
        "/auth/login",
        json={"email": candidate_a.email, "password": "test-pass-123"},
    )
    session_cookie = next(
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(AUTH_COOKIE_NAME)
    )
    assert "Secure" in session_cookie
    assert "HttpOnly" in session_cookie
