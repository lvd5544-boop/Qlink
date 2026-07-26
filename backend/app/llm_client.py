"""Shared LLM helpers: never block the event loop with sync OpenAI SDKs."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

LLM_TIMEOUT_SECONDS = float(os.getenv("MODEL_LLM_TIMEOUT_SECONDS", "60"))


def model_api_key() -> str:
    return (os.getenv("DEEPSEEK_API_KEY") or "").strip()


def model_base_url() -> str:
    return os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")


async def run_in_thread(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run blocking SDK/network work off the event loop with a hard timeout."""
    return await asyncio.wait_for(
        asyncio.to_thread(fn, *args, **kwargs),
        timeout=LLM_TIMEOUT_SECONDS,
    )


async def async_chat_completion(
    *,
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2000,
    response_format: dict | None = None,
) -> Any:
    """Prefer AsyncOpenAI; fall back to threaded sync client if unavailable."""
    api_key = model_api_key()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    model_name = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    kwargs: dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, base_url=model_base_url())
        return await asyncio.wait_for(
            client.chat.completions.create(**kwargs),
            timeout=LLM_TIMEOUT_SECONDS,
        )
    except ImportError:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=model_base_url())
        return await run_in_thread(client.chat.completions.create, **kwargs)
