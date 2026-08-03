"""Shared LLM helpers via the PR10 Model Gateway (no direct provider SDK here)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

from .ai.config import primary_api_key, primary_base_url, request_timeout_seconds
from .ai.errors import AIUnavailableError
from .ai.gateway import InvocationContext, gateway_run
from .ai.task_profiles import model_for

T = TypeVar("T")

LLM_TIMEOUT_SECONDS = request_timeout_seconds()


def model_api_key() -> str:
    """Compatibility shim: reports whether a provider key exists (not the raw key to logs)."""
    return primary_api_key()


def model_base_url() -> str:
    return primary_base_url()


def default_model_name(task: str = "generic_chat") -> str:
    return model_for(task)


async def run_in_thread(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run blocking work off the event loop with a hard timeout."""
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
    tools: list | None = None,
    tool_choice: Any = None,
    task: str = "generic_chat",
    user_id: str | None = None,
    require_json: bool = False,
) -> Any:
    """Chat completion through the gateway provider adapter."""
    if not model_api_key():
        raise AIUnavailableError("AI provider API key is not configured")

    payload: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    if tools is not None:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    if model:
        payload["_explicit_model"] = model

    result = await gateway_run(
        task=task,
        payload=payload,
        schema=None,
        context=InvocationContext(user_id=user_id),
        require_json=require_json,
    )
    if result.raw_response is not None:
        return result.raw_response

    class _Msg:
        content = result.raw_text
        tool_calls = None

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]
        usage = result.usage
        id = result.provider_request_id

    return _Resp()


def sync_chat_completion(
    *,
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2000,
    response_format: dict | None = None,
    tools: list | None = None,
    tool_choice: Any = None,
    task: str = "generic_chat",
) -> Any:
    """Sync wrapper for threaded callers; still goes through the gateway."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            async_chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                tools=tools,
                tool_choice=tool_choice,
                task=task,
                require_json=False,
            )
        )
    # Already inside an event loop (rare): use provider sync adapter only.
    from .ai.providers.openai_compatible import OpenAICompatibleProvider

    if not model_api_key():
        raise AIUnavailableError("AI provider API key is not configured")
    provider = OpenAICompatibleProvider()
    kwargs: dict[str, Any] = {
        "model": model or default_model_name(task),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    if tools is not None:
        kwargs["tools"] = tools
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice
    return provider.chat_completions_create_sync(**kwargs)