"""Data source registry helpers (PR10)."""

from __future__ import annotations

from typing import Any

LAYER_E = "E"
FORMAL_PROFILE_LAYERS = frozenset({"A", "B", "C", "D"})
SOURCE_STATUSES = frozenset({"pending_review", "approved", "restricted", "revoked"})
SOURCE_LAYERS = frozenset({"A", "B", "C", "D", "E"})
VERSION_STATUSES = frozenset({"pending_validation", "published", "superseded", "revoked"})
FORMAL_PROFILE_USE = "formal_profile"
FORUM_SOURCE_KINDS = frozenset(
    {
        "statistical_forum",
        "demo_preview",
        "forum_statistical",
        "insufficient_forum",
    }
)

_USABLE_STATUSES = frozenset({"approved"})


def is_forum_layer_e(source_kind: str | None) -> bool:
    return (source_kind or "").strip() in FORUM_SOURCE_KINDS


def assert_source_usable_for_formal_profile(source: dict[str, Any]) -> None:
    status = (source.get("status") or "").strip()
    layer = (source.get("layer") or "").strip().upper()
    if status not in _USABLE_STATUSES:
        raise PermissionError(f"source status {status!r} cannot be used for formal profiles")
    if layer == LAYER_E or layer not in FORMAL_PROFILE_LAYERS:
        raise PermissionError(f"source layer {layer!r} cannot be used for formal profiles")
    if "allowed_product_uses" in source:
        allowed_uses = {str(item).strip() for item in source.get("allowed_product_uses") or []}
        if FORMAL_PROFILE_USE not in allowed_uses:
            raise PermissionError("source is not licensed for formal_profile use")


def assert_source_version_usable(
    source: dict[str, Any],
    version: dict[str, Any],
    *,
    now: Any = None,
) -> None:
    """Reject unreviewed, expired, superseded, or revoked source versions."""
    from datetime import datetime, timezone

    assert_source_usable_for_formal_profile(source)
    if (version.get("status") or "").strip() != "published":
        raise PermissionError("source version is not published")
    if version.get("superseded_by_version_id"):
        raise PermissionError("source version is superseded")
    expires_at = version.get("expires_at")
    current = now or datetime.now(timezone.utc)
    if expires_at is not None:
        if getattr(expires_at, "tzinfo", None) is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= current:
            raise PermissionError("source version is expired")


def public_source_view(row: dict[str, Any]) -> dict[str, Any]:
    """Strip contract secrets while exposing status for admin/ops UI."""
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "owner_organization": row.get("owner_organization"),
        "acquisition_method": row.get("acquisition_method"),
        "license_name": row.get("license_name"),
        "allowed_product_uses": row.get("allowed_product_uses") or [],
        "training_allowed": bool(row.get("training_allowed")),
        "contains_personal_data": bool(row.get("contains_personal_data")),
        "processing_region": row.get("processing_region"),
        "attribution_text": row.get("attribution_text"),
        "status": row.get("status"),
        "layer": row.get("layer"),
        "scope": row.get("scope") or {},
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        # Explicitly omit license_url / contract_ref / deletion_contact secrets.
    }
