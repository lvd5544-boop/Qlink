"""PR7 background job retry / idempotency helpers."""

from __future__ import annotations

import pytest

from app import background_jobs as jobs


class FakeRedis:
    def __init__(self) -> None:
        self.acked: list[str] = []
        self.streams: dict[str, list[dict]] = {}
        self.kv: dict[str, str] = {}
        self.pending: list[tuple[str, dict]] = []
        self.transaction_calls = 0

    def pipeline(self, transaction=True):
        assert transaction is True
        self.transaction_calls += 1
        return FakePipeline(self)

    async def xack(self, stream, group, message_id):
        self.acked.append(message_id)

    async def xadd(self, stream, fields, maxlen=None, approximate=None):
        self.streams.setdefault(stream, []).append(dict(fields))
        return f"{stream}-{len(self.streams[stream])}"

    async def get(self, key):
        return self.kv.get(key)

    async def set(self, key, value, ex=None):
        self.kv[key] = value

    async def hset(self, key, mapping=None, **kwargs):
        bucket = self.kv.setdefault(f"hash:{key}", {})
        if mapping:
            bucket.update(mapping)
        bucket.update(kwargs)
        self.kv[f"hash:{key}"] = bucket
        return len(mapping or {}) + len(kwargs)

    async def expire(self, key, ttl):
        return True

    async def hgetall(self, key):
        return dict(self.kv.get(f"hash:{key}") or {})

    async def xautoclaim(
        self,
        stream,
        group,
        consumer,
        min_idle_time,
        start_id,
        count,
    ):
        assert (stream, group) == (jobs.STREAM, jobs.GROUP)
        assert consumer
        assert min_idle_time == jobs.PENDING_CLAIM_IDLE_MS
        assert start_id == "0-0"
        return ("0-0", list(self.pending[:count]), [])


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.operations = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def xadd(self, *args, **kwargs):
        self.operations.append(("xadd", args, kwargs))
        return self

    def xack(self, *args, **kwargs):
        self.operations.append(("xack", args, kwargs))
        return self

    def set(self, *args, **kwargs):
        self.operations.append(("set", args, kwargs))
        return self

    async def execute(self):
        results = []
        for method, args, kwargs in self.operations:
            results.append(await getattr(self.redis, method)(*args, **kwargs))
        return results


@pytest.mark.asyncio
async def test_failed_job_is_requeued_under_max_attempts(monkeypatch):
    redis = FakeRedis()
    fields = {
        "type": "resume_match",
        "payload": '{"resume_id":"r1"}',
        "attempt": "0",
        "idempotency_key": "resume_match:r1",
    }

    async def boom(_fields):
        raise RuntimeError("boom")

    monkeypatch.setattr(jobs, "_handle", boom)
    await jobs._process_message(redis, "1-0", fields)
    assert "1-0" in redis.acked
    assert len(redis.streams[jobs.STREAM]) == 1
    assert redis.streams[jobs.STREAM][0]["attempt"] == "1"
    assert jobs.DEAD_LETTER_STREAM not in redis.streams
    assert redis.transaction_calls == 1


@pytest.mark.asyncio
async def test_failed_job_goes_to_dlq_after_max_attempts(monkeypatch):
    redis = FakeRedis()
    fields = {
        "type": "resume_match",
        "payload": '{"resume_id":"r1"}',
        "attempt": str(jobs.MAX_ATTEMPTS - 1),
        "idempotency_key": "resume_match:r1",
    }

    async def boom(_fields):
        raise RuntimeError("boom")

    monkeypatch.setattr(jobs, "_handle", boom)
    await jobs._process_message(redis, "2-0", fields)
    assert jobs.DEAD_LETTER_STREAM in redis.streams
    assert len(redis.streams[jobs.DEAD_LETTER_STREAM]) == 1
    assert redis.transaction_calls == 1


@pytest.mark.asyncio
async def test_idempotent_skip_acks_without_rerun(monkeypatch):
    redis = FakeRedis()
    key = jobs._idempotency_redis_key("resume_match:r1")
    redis.kv[key] = "prior"
    called = {"n": 0}

    async def track(_fields):
        called["n"] += 1

    monkeypatch.setattr(jobs, "_handle", track)
    await jobs._process_message(
        redis,
        "3-0",
        {
            "type": "resume_match",
            "payload": '{"resume_id":"r1"}',
            "attempt": "0",
            "idempotency_key": "resume_match:r1",
        },
    )
    assert called["n"] == 0
    assert "3-0" in redis.acked


@pytest.mark.asyncio
async def test_success_marks_done_and_acks_atomically(monkeypatch):
    redis = FakeRedis()

    async def ok(_fields):
        return None

    monkeypatch.setattr(jobs, "_handle", ok)
    await jobs._process_message(
        redis,
        "4-0",
        {
            "type": "resume_match",
            "payload": '{"resume_id":"r1"}',
            "attempt": "0",
            "idempotency_key": "resume_match:r1",
        },
    )
    assert redis.kv[jobs._idempotency_redis_key("resume_match:r1")] == "4-0"
    assert "4-0" in redis.acked
    assert redis.transaction_calls == 1


@pytest.mark.asyncio
async def test_stale_pending_messages_are_reclaimed():
    redis = FakeRedis()
    redis.pending = [
        (
            "5-0",
            {
                "type": "resume_match",
                "payload": '{"resume_id":"r1"}',
                "attempt": "1",
            },
        )
    ]

    claimed = await jobs._claim_stale_messages(redis, "worker-test")
    assert claimed == redis.pending
