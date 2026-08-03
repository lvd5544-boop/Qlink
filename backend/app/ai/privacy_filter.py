"""Privacy helpers for AI audit logging."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PHONE_RE = re.compile(r"(?:\+?\d[\d\- ]{8,}\d)")


def hash_payload(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def redact_text(text: str, *, keep: int = 24) -> str:
    value = text or ""
    value = _EMAIL_RE.sub("[redacted-email]", value)
    value = _PHONE_RE.sub("[redacted-phone]", value)
    if len(value) <= keep:
        return value
    return value[:keep] + f"…(+{len(value) - keep} chars)"


def assert_no_pii_in_log_payload(payload: Any) -> None:
    blob = json.dumps(payload, ensure_ascii=False, default=str)
    if _EMAIL_RE.search(blob):
        raise AssertionError("log payload contains email")
    if "负责支付核心" in blob and len(blob) > 80:
        raise AssertionError("log payload appears to contain full resume text")
