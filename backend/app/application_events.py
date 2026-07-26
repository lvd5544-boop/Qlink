"""Application SSE event bus with Redis fan-out for multi-worker deployments."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, Set

logger = logging.getLogger(__name__)


class ApplicationEventBus:
    """Redis pub/sub in production, process-local queues in tests/development."""

    def __init__(self) -> None:
        self._subs: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._user_subs: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._redis = None
        self._listeners: dict[asyncio.Queue, tuple[asyncio.Task, object]] = {}

    def configure(self, redis_client) -> None:
        self._redis = redis_client

    def _use_redis(self) -> bool:
        configured = os.getenv("APPLICATION_EVENT_BACKEND", "").strip().lower()
        if configured:
            return configured == "redis"
        return os.getenv("ENV", "development").strip().lower() == "production"

    @staticmethod
    def _application_channel(application_id: str) -> str:
        return f"application-events:application:{application_id}"

    @staticmethod
    def _user_channel(user_id: str) -> str:
        return f"application-events:user:{user_id}"

    async def _listen(self, pubsub, queue: asyncio.Queue) -> None:
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                raw = message.get("data")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                try:
                    queue.put_nowait(raw)
                except asyncio.QueueFull:
                    logger.warning("SSE Redis queue full")
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("SSE Redis subscription stopped unexpectedly")

    async def _subscribe_redis(self, channel: str, queue: asyncio.Queue) -> None:
        if self._redis is None:
            raise RuntimeError("Redis event backend is configured but unavailable")
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        task = asyncio.create_task(self._listen(pubsub, queue))
        self._listeners[queue] = (task, pubsub)

    async def subscribe_application(self, application_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        if self._use_redis():
            await self._subscribe_redis(self._application_channel(application_id), q)
            return q
        self._subs[application_id].add(q)
        return q

    async def subscribe_user(self, user_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        if self._use_redis():
            await self._subscribe_redis(self._user_channel(user_id), q)
            return q
        self._user_subs[user_id].add(q)
        return q

    async def _close_listener(self, q: asyncio.Queue) -> bool:
        listener = self._listeners.pop(q, None)
        if listener is None:
            return False
        task, pubsub = listener
        task.cancel()
        await pubsub.aclose()
        return True

    async def unsubscribe_application(self, application_id: str, q: asyncio.Queue) -> None:
        if await self._close_listener(q):
            return
        self._subs[application_id].discard(q)
        if not self._subs[application_id]:
            self._subs.pop(application_id, None)

    async def unsubscribe_user(self, user_id: str, q: asyncio.Queue) -> None:
        if await self._close_listener(q):
            return
        self._user_subs[user_id].discard(q)
        if not self._user_subs[user_id]:
            self._user_subs.pop(user_id, None)

    async def publish(
        self,
        *,
        application_id: str,
        event_type: str,
        payload: dict,
        candidate_id: str | None = None,
        employer_id: str | None = None,
    ) -> None:
        event = {
            "type": event_type,
            "application_id": application_id,
            "payload": payload,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        raw = json.dumps(event, ensure_ascii=False)
        if self._use_redis():
            if self._redis is None:
                raise RuntimeError("Redis event backend is configured but unavailable")
            channels = [self._application_channel(application_id)]
            channels.extend(
                self._user_channel(uid) for uid in filter(None, [candidate_id, employer_id])
            )
            await asyncio.gather(*(self._redis.publish(channel, raw) for channel in channels))
            return

        for q in list(self._subs.get(application_id, set())):
            try:
                q.put_nowait(raw)
            except asyncio.QueueFull:
                logger.warning("SSE queue full for application %s", application_id)

        for uid in filter(None, [candidate_id, employer_id]):
            for q in list(self._user_subs.get(uid, set())):
                try:
                    q.put_nowait(raw)
                except asyncio.QueueFull:
                    logger.warning("SSE queue full for user %s", uid)


event_bus = ApplicationEventBus()


async def sse_event_stream(queue: asyncio.Queue) -> AsyncIterator[str]:
    """将队列事件格式化为 SSE data 行；附带心跳。"""
    try:
        while True:
            try:
                raw = await asyncio.wait_for(queue.get(), timeout=25.0)
                yield f"data: {raw}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'ping', 'ts': datetime.now(timezone.utc).isoformat()})}\n\n"
    except asyncio.CancelledError:
        return
