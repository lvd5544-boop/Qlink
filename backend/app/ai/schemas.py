"""Shared schema helpers for gateway structured outputs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenericJSONObject(BaseModel):
    """Loose object wrapper when callers validate further downstream."""

    model_config = {"extra": "allow"}


class ChatTextResult(BaseModel):
    text: str = Field(min_length=1)
