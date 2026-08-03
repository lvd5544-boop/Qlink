"""Small, deterministic text repairs for externally supplied job data."""

from __future__ import annotations

import html
from typing import Any


_MOJIBAKE_HINTS = frozenset("ÃÂâØÙÐÑð�")


def _badness(value: str) -> int:
    return sum(value.count(marker) for marker in _MOJIBAKE_HINTS) + sum(
        2 for character in value if "\x80" <= character <= "\x9f"
    )


def repair_mojibake(value: str | None) -> str:
    """Repair common UTF-8-as-Latin-1/Windows-1252 damage without guessing freely."""
    current = html.unescape(str(value or ""))
    for _ in range(2):
        candidates = [current]
        for encoding in ("latin-1", "cp1252"):
            try:
                # External APIs occasionally truncate a final multi-byte
                # character. Repair the valid prefix and discard only the
                # broken tail instead of abandoning the whole string.
                candidates.append(
                    current.encode(encoding).decode("utf-8", errors="replace")
                )
            except UnicodeEncodeError:
                continue
        best = min(candidates, key=_badness)
        if _badness(best) >= _badness(current):
            break
        current = best
    return current.replace("\ufffd", "").strip()


def repair_text_tree(value: Any) -> Any:
    """Recursively repair display strings while preserving the payload shape."""
    if isinstance(value, str):
        return repair_mojibake(value)
    if isinstance(value, list):
        return [repair_text_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: repair_text_tree(item) for key, item in value.items()}
    return value
