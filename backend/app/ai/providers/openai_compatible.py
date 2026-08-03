"""OpenAI-compatible provider adapter (Aliyun Model Studio / DeepSeek / etc.)."""

from __future__ import annotations

import asyncio
from typing import Any

from openai import AsyncOpenAI, OpenAI

from ..config import primary_api_key, primary_base_url, request_timeout_seconds


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else primary_api_key()).strip()
        self.base_url = (base_url if base_url is not None else primary_base_url()).rstrip(
            "/"
        )
        self.timeout = (
            timeout if timeout is not None else request_timeout_seconds()
        )

    def _ensure_key(self) -> None:
        if not self.api_key:
            raise RuntimeError("AI provider API key is not configured")

    async def chat_completions_create(self, **kwargs: Any) -> Any:
        self._ensure_key()
        base_url = self.base_url or None
        try:
            client = AsyncOpenAI(api_key=self.api_key, base_url=base_url)
            return await asyncio.wait_for(
                client.chat.completions.create(**kwargs),
                timeout=self.timeout,
            )
        except ImportError:
            return await asyncio.wait_for(
                asyncio.to_thread(self.chat_completions_create_sync, **kwargs),
                timeout=self.timeout,
            )

    def chat_completions_create_sync(self, **kwargs: Any) -> Any:
        """Sync path for legacy threaded parsers; still provider-adapter only."""
        self._ensure_key()
        base_url = self.base_url or None
        client = OpenAI(api_key=self.api_key, base_url=base_url)
        return client.chat.completions.create(**kwargs)


class AliyunModelStudioProvider(OpenAICompatibleProvider):
    """Aliyun Model Studio uses an OpenAI-compatible chat API surface."""

    name = "aliyun_model_studio"
