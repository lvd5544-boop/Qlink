"""Provider usage normalization and precise admin-only cost events."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .models_db import ProviderCostEvent


def _read_value(source: Any, *names: str, default: Any = 0) -> Any:
    for name in names:
        if isinstance(source, dict) and source.get(name) is not None:
            return source[name]
        value = getattr(source, name, None)
        if value is not None:
            return value
    return default


def extract_provider_usage(
    response: Any,
    *,
    provider: str,
    requested_model: str,
) -> dict:
    usage = getattr(response, "usage", None) or {}
    details = _read_value(usage, "prompt_tokens_details", default={}) or {}
    input_tokens = int(_read_value(usage, "prompt_tokens", "input_tokens") or 0)
    output_tokens = int(_read_value(usage, "completion_tokens", "output_tokens") or 0)
    cache_hit = int(
        _read_value(
            usage,
            "prompt_cache_hit_tokens",
            default=_read_value(details, "cached_tokens", default=0),
        )
        or 0
    )
    cache_miss = int(_read_value(usage, "prompt_cache_miss_tokens", default=0) or 0)
    if cache_hit and not cache_miss:
        cache_miss = max(0, input_tokens - cache_hit)

    return {
        "provider": provider,
        "model": str(getattr(response, "model", None) or requested_model),
        "provider_request_id": (str(getattr(response, "id", "")) or None),
        "input_tokens": max(0, input_tokens),
        "output_tokens": max(0, output_tokens),
        "cache_hit_tokens": max(0, cache_hit),
        "cache_miss_tokens": max(0, cache_miss),
    }


def _price(name: str) -> Optional[Decimal]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise RuntimeError(f"{name} 必须是非负十进制数") from exc
    if value < 0:
        raise RuntimeError(f"{name} 必须是非负十进制数")
    return value


def calculate_cost_microunits(usage: dict) -> tuple[int, str]:
    """Calculate CNY millionths using versioned CNY-per-million-token prices."""
    input_price = _price("DEEPSEEK_INPUT_PRICE_CNY_PER_MILLION")
    output_price = _price("DEEPSEEK_OUTPUT_PRICE_CNY_PER_MILLION")
    cache_hit_price = _price("DEEPSEEK_CACHE_HIT_PRICE_CNY_PER_MILLION")
    cache_miss_price = _price("DEEPSEEK_CACHE_MISS_PRICE_CNY_PER_MILLION")
    price_version = os.getenv("DEEPSEEK_PRICE_VERSION", "unconfigured")

    if input_price is None or output_price is None:
        return 0, "unconfigured"

    cache_hit = int(usage.get("cache_hit_tokens") or 0)
    cache_miss = int(usage.get("cache_miss_tokens") or 0)
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)

    if cache_hit or cache_miss:
        input_cost = Decimal(cache_hit) * (cache_hit_price or input_price) + Decimal(cache_miss) * (
            cache_miss_price or input_price
        )
    else:
        input_cost = Decimal(input_tokens) * input_price
    # CNY / 1M tokens × token count × 1M micro-CNY / CNY.
    micro_cny = input_cost + Decimal(output_tokens) * output_price
    return (
        int(micro_cny.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        price_version,
    )


async def record_provider_cost_event(
    db: AsyncSession,
    *,
    reservation_id: Optional[str],
    user_id: Optional[str],
    organization_id: Optional[str],
    feature: str,
    prompt_version: str,
    provider_status: str,
    usage: Optional[dict] = None,
    requested_model: Optional[str] = None,
) -> ProviderCostEvent:
    normalized = usage or {
        "provider": "deepseek",
        "model": requested_model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "provider_request_id": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_hit_tokens": 0,
        "cache_miss_tokens": 0,
    }
    cost_microunits, price_version = calculate_cost_microunits(normalized)
    event = ProviderCostEvent(
        reservation_id=reservation_id,
        user_id=user_id,
        organization_id=organization_id,
        feature=feature,
        provider=normalized.get("provider") or "deepseek",
        model=normalized.get("model") or requested_model or "unknown",
        model_version=normalized.get("model_version"),
        prompt_version=prompt_version,
        provider_request_id=normalized.get("provider_request_id"),
        input_tokens=int(normalized.get("input_tokens") or 0),
        output_tokens=int(normalized.get("output_tokens") or 0),
        cache_hit_tokens=int(normalized.get("cache_hit_tokens") or 0),
        cache_miss_tokens=int(normalized.get("cache_miss_tokens") or 0),
        currency="CNY",
        cost_microunits=cost_microunits,
        cost_minor_units=(cost_microunits + 5000) // 10000,
        price_version=price_version,
        provider_status=provider_status,
    )
    db.add(event)
    return event


async def record_metering_cost_if_called(
    db: AsyncSession,
    *,
    metering: dict,
    reservation_id: Optional[str],
    user_id: Optional[str],
    organization_id: Optional[str],
    feature: str,
    prompt_version: str,
) -> Optional[ProviderCostEvent]:
    if not metering.get("model_called"):
        return None
    return await record_provider_cost_event(
        db,
        reservation_id=reservation_id,
        user_id=user_id,
        organization_id=organization_id,
        feature=feature,
        prompt_version=prompt_version,
        provider_status=metering.get("provider_status") or "unknown",
        usage=metering.get("provider_usage"),
    )
