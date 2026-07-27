"""
PR0 安全测试骨架：当前行为下应能通过的权限与鉴权断言。

跨租户 Findings（审计 IDOR 等）见 test_security_findings_baseline.py（xfail）。
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_is_public(client):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json().get("status") == "ok"


@pytest.mark.asyncio
async def test_unauthenticated_cannot_access_protected_resume_list(client, candidate_a):
    res = await client.get(f"/resumes/{candidate_a.id}")
    assert res.status_code in {401, 403}


@pytest.mark.asyncio
async def test_unauthenticated_cannot_access_usage(client):
    res = await client.get("/usage/me")
    assert res.status_code in {401, 403}


@pytest.mark.asyncio
async def test_unauthenticated_cannot_access_application_messages(client, application_a):
    res = await client.get(f"/applications/{application_a.id}/messages")
    assert res.status_code in {401, 403}


@pytest.mark.asyncio
async def test_candidate_a_cannot_read_candidate_b_resume_list(
    client, auth_header, candidate_a, candidate_b, resume_b
):
    res = await client.get(
        f"/resumes/{candidate_b.id}",
        headers=auth_header(candidate_a),
    )
    assert res.status_code in {403, 404}


@pytest.mark.asyncio
async def test_candidate_a_cannot_read_candidate_b_resume_detail(
    client, auth_header, candidate_a, resume_b
):
    res = await client.get(
        f"/resume/{resume_b.id}",
        headers=auth_header(candidate_a),
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_candidate_a_cannot_delete_candidate_b_resume(
    client, auth_header, candidate_a, resume_b
):
    res = await client.delete(
        f"/resumes/{resume_b.id}",
        headers=auth_header(candidate_a),
    )
    assert res.status_code in {403, 404}


@pytest.mark.asyncio
async def test_candidate_cannot_call_employer_audit_endpoint(
    client, auth_header, candidate_a, job_a, resume_a
):
    res = await client.get(
        f"/applications/job/{job_a.id}/resume/{resume_a.id}/credibility-audit",
        headers=auth_header(candidate_a),
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_employer_a_cannot_read_employer_b_application_messages(
    client, auth_header, employer_a, application_b, message_a
):
    # message_a 属于 application_a；此处验证 B 的申请消息对 A 不可见
    res = await client.get(
        f"/applications/{application_b.id}/messages",
        headers=auth_header(employer_a),
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_candidate_a_cannot_read_application_b_messages(
    client, auth_header, candidate_a, application_b
):
    res = await client.get(
        f"/applications/{application_b.id}/messages",
        headers=auth_header(candidate_a),
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_missing_resume_id_does_not_leak_other_tenant(client, auth_header, candidate_a):
    res = await client.get(
        "/resume/00000000-0000-0000-0000-000000000099",
        headers=auth_header(candidate_a),
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_missing_application_id_is_not_found(client, auth_header, employer_a):
    res = await client.get(
        "/applications/00000000-0000-0000-0000-000000000099/messages",
        headers=auth_header(employer_a),
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_role_matrix_candidate_can_read_own_resume(
    client, auth_header, candidate_a, resume_a
):
    res = await client.get(
        f"/resume/{resume_a.id}",
        headers=auth_header(candidate_a),
    )
    assert res.status_code == 200
    assert res.json()["id"] == str(resume_a.id)


@pytest.mark.asyncio
async def test_role_matrix_employer_can_read_own_application_messages(
    client, auth_header, employer_a, application_a, message_a
):
    res = await client.get(
        f"/applications/{application_a.id}/messages",
        headers=auth_header(employer_a),
    )
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    assert any(m.get("id") == str(message_a.id) for m in res.json())


@pytest.mark.asyncio
async def test_role_matrix_admin_is_distinct_role(admin_user):
    assert admin_user.role == "admin"


@pytest.mark.asyncio
async def test_fixtures_expose_two_claim_threads(application_a):
    threads = (application_a.pipeline_meta or {}).get("claim_threads") or {}
    assert len(threads) >= 2
    assert "work_experience_0_action_0" in threads
    assert "work_experience_0_action_1" in threads


def test_sse_routes_registered_distinct_paths():
    """
    ASGI 路由级可达性：/stream/me 与 /{application_id}/events 同时注册。

    不直接枚举 ``app.routes``：新版本 FastAPI 可将 include_router 保留为
    内部包装对象，路径不再位于顶层 ``route.path``，但真实 ASGI 分派仍正确。
    未认证请求必须到达鉴权层（401/403），而非被动态路由或缺失路由误判为 404。
    """
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    stream_me = client.get("/applications/stream/me")
    application_events = client.get("/applications/not-a-real-id/events")
    assert stream_me.status_code in {401, 403}, stream_me.text
    assert application_events.status_code in {401, 403}, application_events.text
