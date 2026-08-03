"""Provider adapter base."""

from __future__ import annotations

from typing import Any, Protocol


class ChatProvider(Protocol):
    name: str

    async def chat_completions_create(self, **kwargs: Any) -> Any: ...
