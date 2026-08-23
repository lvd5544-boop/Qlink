from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import engine
from app.models_db import UsageEvent


pytestmark = pytest.mark.asyncio


async def test_quota_reservation_is_idempotent_and_finalizes_once(
    db_session, candidate_a, monkeypatch
):
    from app.models_db import UsageReservation
    from app.usage_metering import (
        finalize_quota,
        reserve_quota,
    )

    monkeypatch.setenv("METERING_ENABLED", "true")
    key = f"idem-{uuid4()}"

    first = await reserve_quota(
        db_session,
        user_id=str(candidate_a.id),
        feature="resume_coach",
        idempotency_key=key,
        quota_override=1,
    )
    repeated = await reserve_quota(
        db_session,
        user_id=str(candidate_a.id),
        feature="resume_coach",
        idempotency_key=key,
        quota_override=1,
    )

    assert first["reservation_id"] == repeated["reservation_id"]
    assert first["created"] is True
    assert repeated["created"] is False

    await finalize_quota(db_session, first["reservation_id"], succeeded=True)
    await finalize_quota(db_session, first["reservation_id"], succeeded=True)

    reservation_count = (
        await db_session.execute(select(func.count()).select_from(UsageReservation))
    ).scalar_one()
    event_count = (
        await db_session.execute(select(func.count()).select_from(UsageEvent))
    ).scalar_one()
    assert reservation_count == 1
    assert event_count == 1


async def test_same_idempotency_key_with_different_payload_is_rejected(
    db_session, candidate_a, monkeypatch
):
    from app.usage_metering import reserve_quota

    monkeypatch.setenv("METERING_ENABLED", "true")
    await reserve_quota(
        db_session,
        user_id=str(candidate_a.id),
        feature="resume_coach",
        idempotency_key="same-key-different-payload",
        meta={"resume_id": "resume-a"},
        quota_override=2,
    )
    with pytest.raises(HTTPException) as exc_info:
        await reserve_quota(
            db_session,
            user_id=str(candidate_a.id),
            feature="resume_coach",
            idempotency_key="same-key-different-payload",
            meta={"resume_id": "resume-b"},
            quota_override=2,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "idempotency_conflict"


async def test_monthly_billing_period_uses_china_timezone(monkeypatch):
    from app.usage_metering import _month_key

    monkeypatch.setenv("BILLING_TIMEZONE", "Asia/Shanghai")
    # 北京时间已进入 8 月，UTC 仍是 7 月。
    at_boundary = datetime(2026, 7, 31, 16, 30, tzinfo=timezone.utc)
    assert _month_key(at_boundary) == "2026-08"


async def test_failed_quota_reservation_releases_capacity(db_session, candidate_a, monkeypatch):
    from app.models_db import UsageReservation
    from app.usage_metering import finalize_quota, reserve_quota

    monkeypatch.setenv("METERING_ENABLED", "true")
    key = f"failed-{uuid4()}"
    first = await reserve_quota(
        db_session,
        user_id=str(candidate_a.id),
        feature="evidence_regenerate",
        idempotency_key=key,
        quota_override=1,
    )
    await finalize_quota(
        db_session,
        first["reservation_id"],
        succeeded=False,
        failure_reason="model_error",
    )
    # 已确认失败的同一业务操作可使用原幂等键重试；不能卡在 replay 冲突。
    second = await reserve_quota(
        db_session,
        user_id=str(candidate_a.id),
        feature="evidence_regenerate",
        idempotency_key=key,
        quota_override=1,
    )
    assert second["created"] is True
    assert second["reservation_id"] == first["reservation_id"]
    assert second["status"] == "reserved"

    await finalize_quota(db_session, second["reservation_id"], succeeded=True)
    event_count = (
        await db_session.execute(select(func.count()).select_from(UsageEvent))
    ).scalar_one()
    reservation_count = (
        await db_session.execute(select(func.count()).select_from(UsageReservation))
    ).scalar_one()
    assert event_count == 1
    assert reservation_count == 1


async def test_postgres_concurrent_quota_reservation_never_oversells(candidate_a, monkeypatch):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL advisory-lock concurrency contract")

    from app.usage_metering import reserve_quota

    monkeypatch.setenv("METERING_ENABLED", "true")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def attempt(index: int) -> int:
        async with session_factory() as session:
            try:
                await reserve_quota(
                    session,
                    user_id=str(candidate_a.id),
                    feature="credibility_audit",
                    idempotency_key=f"concurrent-{uuid4()}-{index}",
                    quota_override=2,
                )
                return 200
            except HTTPException as exc:
                return exc.status_code

    results = await asyncio.gather(*(attempt(i) for i in range(8)))
    assert results.count(200) == 2
    assert results.count(429) == 6


async def test_postgres_usage_reservation_migration_upgrade_downgrade():
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL migration contract")

    migration_dir = Path(__file__).resolve().parents[1] / "scripts" / "migrations"
    upgrade = (migration_dir / "20260725_pr5_usage_reservations_up.sql").read_text(encoding="utf-8")
    downgrade = (migration_dir / "20260725_pr5_usage_reservations_down.sql").read_text(
        encoding="utf-8"
    )

    async with engine.begin() as connection:
        for sql in (upgrade, upgrade, downgrade, upgrade):
            for statement in (part.strip() for part in sql.split(";")):
                if statement:
                    await connection.exec_driver_sql(statement)

        exists = await connection.exec_driver_sql(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'usage_reservations'
            """
        )
        assert exists.scalar() == 1


@pytest.mark.parametrize(
    ("source", "generated", "violated"),
    [
        (
            "参与订单模块开发，优化缓存策略",
            "参与订单模块开发，优化缓存策略，并实现海外市场增长",
            True,
        ),
        (
            "负责订单模块重构",
            "负责订单模块重构，将延迟降低35%",
            True,
        ),
        (
            "参与订单模块开发，优化缓存策略",
            "参与订单模块研发并改进缓存方案",
            False,
        ),
        (
            "负责订单模块 用户回答延迟降低35%",
            "负责订单模块，将延迟降低35%",
            False,
        ),
        (
            "参与订单模块开发",
            "主导订单模块开发",
            True,
        ),
        (
            "参与订单模块开发并持续优化缓存策略，负责日常问题排查和稳定性维护",
            "参与订单模块开发并基于阿里云持续优化缓存策略，负责日常问题排查和稳定性维护",
            True,
        ),
        (
            "参与订单模块开发，负责日常问题排查",
            "参与订单模块开发并负责日常问题排查",
            False,
        ),
    ],
)
async def test_fidelity_covers_fabrication_numbers_synonyms_and_role_upgrade(
    source, generated, violated
):
    from app.evidence_followup import assess_fidelity

    result = assess_fidelity(source, generated)
    assert result["violated"] is violated
    assert result["version"]
    assert "coverage" in result


async def test_websocket_query_token_is_disabled_by_default(monkeypatch):
    from app.websocket_auth import query_token_compatibility_enabled

    monkeypatch.delenv("WS_ALLOW_QUERY_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    assert query_token_compatibility_enabled() is False

    monkeypatch.setenv("WS_ALLOW_QUERY_TOKEN", "true")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("AUTH_STATE_BACKEND", "local")
    assert query_token_compatibility_enabled() is False


class _FakeWebSocket:
    def __init__(self, first_message: str, query_params=None, cookies=None, headers=None):
        self.first_message = first_message
        self.query_params = query_params or {}
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.sent: list[str] = []
        self.closed = None

    async def receive_text(self):
        return self.first_message

    async def send_text(self, value: str):
        self.sent.append(value)

    async def close(self, code: int, reason: str):
        self.closed = (code, reason)


async def test_websocket_authenticates_first_message_before_resource_access(
    db_session, candidate_a, resume_a
):
    from app.auth import create_access_token
    from app.websocket_auth import authenticate_websocket

    token = create_access_token({"sub": str(candidate_a.id)})
    websocket = _FakeWebSocket(json.dumps({"type": "auth", "token": token}))
    user = await authenticate_websocket(
        websocket,
        db_session,
        user_id=str(candidate_a.id),
        resume_id=str(resume_a.id),
        application_id=None,
    )
    assert user is candidate_a
    assert websocket.closed is None
    assert json.loads(websocket.sent[0]) == {"type": "auth_ok"}


async def test_websocket_rejects_resume_owned_by_another_candidate(
    db_session, candidate_a, resume_b
):
    from app.auth import create_access_token
    from app.websocket_auth import authenticate_websocket

    token = create_access_token({"sub": str(candidate_a.id)})
    websocket = _FakeWebSocket(json.dumps({"type": "auth", "token": token}))
    user = await authenticate_websocket(
        websocket,
        db_session,
        user_id=str(candidate_a.id),
        resume_id=str(resume_b.id),
        application_id=None,
    )
    assert user is None
    assert websocket.closed[0] == 1008
    assert websocket.sent == []


async def test_websocket_accepts_httponly_cookie_with_allowed_origin(
    db_session, candidate_a, resume_a, monkeypatch
):
    from app.auth import AUTH_COOKIE_NAME, create_access_token
    from app.websocket_auth import authenticate_websocket

    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("AUTH_STATE_BACKEND", "local")
    monkeypatch.setenv("PUBLIC_ORIGIN", "https://jobs.example.test")
    token = create_access_token({"sub": str(candidate_a.id)})
    websocket = _FakeWebSocket(
        json.dumps({"type": "auth", "requested_uses": {"resume_write": True}}),
        cookies={AUTH_COOKIE_NAME: token},
        headers={"origin": "https://jobs.example.test"},
    )
    user = await authenticate_websocket(
        websocket,
        db_session,
        user_id=str(candidate_a.id),
        resume_id=str(resume_a.id),
        application_id=None,
    )
    assert user is candidate_a
    assert websocket.closed is None
    assert json.loads(websocket.sent[0]) == {"type": "auth_ok"}


async def test_websocket_cookie_rejects_cross_origin(db_session, candidate_a, monkeypatch):
    from app.auth import AUTH_COOKIE_NAME, create_access_token
    from app.websocket_auth import authenticate_websocket

    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("PUBLIC_ORIGIN", "https://jobs.example.test")
    websocket = _FakeWebSocket(
        json.dumps({"type": "auth"}),
        cookies={AUTH_COOKIE_NAME: create_access_token({"sub": str(candidate_a.id)})},
        headers={"origin": "https://evil.example"},
    )
    user = await authenticate_websocket(
        websocket,
        db_session,
        user_id=str(candidate_a.id),
        resume_id=None,
        application_id=None,
    )
    assert user is None
    assert websocket.closed == (1008, "WebSocket 来源无效")


async def test_evidence_writeback_requires_untampered_server_fidelity_proof(
    client, auth_header, db_session, candidate_a, resume_a
):
    from app.models_db import ResumeSuggestion
    from app.resume_suggestion_store import sync_suggestions_for_source

    original = resume_a.parsed_json["work_experience"][0]["description"]
    await sync_suggestions_for_source(
        db_session,
        str(resume_a.id),
        "health_check",
        [
            {
                "id": "pr5-proof",
                "source": "health_check",
                "title": "补充量化",
                "requires_evidence": True,
                "needs_followup": True,
                "original_text": original,
                "patch": {
                    "action": "append_quantification",
                    "section": "work_experience",
                    "index": 0,
                    "value": None,
                    "requires_evidence": True,
                },
            }
        ],
    )
    row = (
        (
            await db_session.execute(
                select(ResumeSuggestion).where(
                    ResumeSuggestion.resume_id == str(resume_a.id),
                    ResumeSuggestion.suggestion_key == "pr5-proof",
                )
            )
        )
        .scalars()
        .one()
    )

    generated = await client.post(
        f"/resumes/{resume_a.id}/evidence-followup/regenerate",
        headers=auth_header(candidate_a),
        json={
            "entry_type": "work",
            "index": 0,
            "answers": [
                {
                    "id": "evidence-p99",
                    "question": "结果？",
                    "answer": "将 P99 从 200ms 降到 120ms",
                }
            ],
            "rewrite_mode": "conservative",
        },
    )
    assert generated.status_code == 200, generated.text
    payload = generated.json()
    patch = {
        "action": "append_quantification",
        "section": "work_experience",
        "index": 0,
        "value": payload["example_after"],
        "evidence_completed": True,
        "evidence_references": payload["evidence_references"],
        "fidelity_result": payload["fidelity_result"],
        "fidelity_proof": payload["fidelity_proof"],
    }

    tampered = await client.post(
        f"/resumes/{resume_a.id}/apply-suggestion",
        headers=auth_header(candidate_a),
        json={
            "suggestion_id": str(row.id),
            "patch": {**patch, "value": f"{patch['value']}，并虚构增长99%"},
        },
    )
    assert tampered.status_code == 400

    applied = await client.post(
        f"/resumes/{resume_a.id}/apply-suggestion",
        headers=auth_header(candidate_a),
        json={"suggestion_id": str(row.id), "patch": patch},
    )
    assert applied.status_code == 200, applied.text
    history = applied.json()["parsed_json"]["_fidelity_history"]
    assert history[-1]["fidelity_result"]["violated"] is False
    assert "evidence-p99" in history[-1]["evidence_references"]


async def test_fidelity_proof_uses_a_dedicated_rotatable_secret(monkeypatch):
    from app.fidelity_proof import create_fidelity_proof, verify_fidelity_proof

    monkeypatch.setenv("FIDELITY_PROOF_SECRET_KEY", "proof-key-a-" + ("a" * 32))
    proof = create_fidelity_proof(
        resume_id="resume-1",
        field_path="work_experience[0].description",
        value="忠实内容",
        fidelity_result={"violated": False},
        evidence_references=["answer-1"],
    )

    # 登录 JWT 密钥轮换不影响使用独立密钥签发的忠实度凭证。
    monkeypatch.setenv("SECRET_KEY", "rotated-access-key-" + ("x" * 32))
    payload = verify_fidelity_proof(
        proof,
        resume_id="resume-1",
        field_path="work_experience[0].description",
        value="忠实内容",
    )
    assert payload["typ"] == "fidelity_proof"

    # 独立凭证密钥自身轮换后，旧凭证应失效。
    monkeypatch.setenv("FIDELITY_PROOF_SECRET_KEY", "proof-key-b-" + ("b" * 32))
    with pytest.raises(HTTPException) as exc_info:
        verify_fidelity_proof(
            proof,
            resume_id="resume-1",
            field_path="work_experience[0].description",
            value="忠实内容",
        )
    assert exc_info.value.status_code == 400


async def test_production_requires_a_dedicated_fidelity_proof_secret(monkeypatch):
    from app.fidelity_proof import validate_fidelity_proof_configuration

    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("FIDELITY_PROOF_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FIDELITY_PROOF_SECRET_KEY"):
        validate_fidelity_proof_configuration()
