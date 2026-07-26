from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.application_events import ApplicationEventBus
from app.background_jobs import enqueue_resume_match
from app.readiness import collect_readiness, model_runtime_mode
from app.schema_version import EXPECTED_MIGRATIONS, inspect_schema
from app.migration_sql import split_sql as _split_sql


@pytest.mark.asyncio
async def test_schema_check_is_read_only_and_reports_missing_ledger(test_engine):
    status = await inspect_schema(test_engine)
    assert status.ready is False
    assert status.applied == ()
    assert status.missing == EXPECTED_MIGRATIONS


@pytest.mark.asyncio
async def test_readiness_reports_rules_only_without_leaking_secrets(
    test_engine,
    monkeypatch,
):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("MODEL_REQUIRED", "false")

    class HealthyRedis:
        async def ping(self):
            return True

        async def get(self, _key):
            return None

    result = await collect_readiness(test_engine, HealthyRedis())
    assert result["checks"]["database"]["ok"] is True
    assert result["checks"]["redis"]["ok"] is True
    assert result["checks"]["background"]["ok"] is True
    assert result["checks"]["model"] == {
        "ok": True,
        "mode": "rules_only",
        "required": False,
    }
    assert model_runtime_mode() == "rules_only"
    assert "DEEPSEEK_API_KEY" not in str(result)


@pytest.mark.asyncio
async def test_in_memory_event_bus_remains_available_for_tests(monkeypatch):
    monkeypatch.setenv("APPLICATION_EVENT_BACKEND", "memory")
    bus = ApplicationEventBus()
    queue = await bus.subscribe_application("application-1")
    await bus.publish(
        application_id="application-1",
        event_type="updated",
        payload={"status": "reviewing"},
        candidate_id="candidate-1",
    )
    raw = await asyncio.wait_for(queue.get(), timeout=0.2)
    assert '"type": "updated"' in raw
    await bus.unsubscribe_application("application-1", queue)


@pytest.mark.asyncio
async def test_redis_event_bus_fans_out_across_channels(monkeypatch):
    monkeypatch.setenv("APPLICATION_EVENT_BACKEND", "redis")
    published = []

    class FakeRedis:
        async def publish(self, channel, raw):
            published.append((channel, raw))

    bus = ApplicationEventBus()
    bus.configure(FakeRedis())
    await bus.publish(
        application_id="application-1",
        event_type="message",
        payload={"body": "hello"},
        candidate_id="candidate-1",
        employer_id="employer-1",
    )
    assert [item[0] for item in published] == [
        "application-events:application:application-1",
        "application-events:user:candidate-1",
        "application-events:user:employer-1",
    ]


@pytest.mark.asyncio
async def test_resume_match_is_enqueued_on_shared_stream():
    calls = []

    class FakeRedis:
        async def xadd(self, stream, fields, **options):
            calls.append((stream, fields, options))
            return "1-0"

        async def hset(self, key, mapping=None, **kwargs):
            return 1

        async def expire(self, key, ttl):
            return True

    job_id = await enqueue_resume_match(FakeRedis(), "resume-1")
    assert job_id
    assert calls[0][0] == "ai-job-platform:background-jobs"
    assert calls[0][1]["type"] == "resume_match"
    assert calls[0][1]["job_id"] == job_id
    assert '"resume_id": "resume-1"' in calls[0][1]["payload"]


def test_migration_sql_is_split_for_asyncpg_prepared_statements():
    assert _split_sql("SELECT 1;\nSELECT 2;") == ["SELECT 1", "SELECT 2"]


def test_backup_restore_use_database_identity_from_container():
    root = Path(__file__).resolve().parents[2]
    backup = (root / "scripts" / "backup.sh").read_text(encoding="utf-8")
    restore = (root / "scripts" / "restore.sh").read_text(encoding="utf-8")

    for script in (backup, restore):
        assert '"$POSTGRES_USER"' in script
        assert '"$POSTGRES_DB"' in script
        assert "${POSTGRES_USER:-appuser}" not in script
        assert "${POSTGRES_DB:-jobplatform}" not in script


def test_restore_recreates_proxy_and_checks_public_readiness():
    root = Path(__file__).resolve().parents[2]
    restore = (root / "scripts" / "restore.sh").read_text(encoding="utf-8")

    assert "compose up -d --force-recreate frontend" in restore
    assert "http://127.0.0.1/api/ready" in restore
    assert 'if [[ "$ready" != "true" ]]' in restore


def test_example_env_does_not_fake_model_configuration():
    root = Path(__file__).resolve().parents[2]
    example = (root / ".env.example").read_text(encoding="utf-8")

    assert "MODEL_REQUIRED=false" in example
    assert "DEEPSEEK_API_KEY=\n" in example
    assert "DEEPSEEK_API_KEY=CHANGE_ME" not in example
