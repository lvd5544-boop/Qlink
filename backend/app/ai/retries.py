"""Retry helpers for AI gateway."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def with_retries(
    fn: Callable[[], Awaitable[T]],
    *,
    retries: int,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    attempt = 0
    while True:
        try:
            return await fn()
        except retry_on:
            if attempt >= retries:
                raise
            attempt += 1
            await asyncio.sleep(min(0.05 * (2**attempt), 0.5))
