"""Signed server proof for evidence-backed resume patches."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import os
from typing import Any

from fastapi import HTTPException
import jwt
from jwt import InvalidTokenError as JWTError

from .auth import ALGORITHM, SECRET_KEY


def _fidelity_proof_secret() -> str:
    """Return the proof-only signing key, with a development compatibility fallback."""
    return os.getenv("FIDELITY_PROOF_SECRET_KEY") or SECRET_KEY


def validate_fidelity_proof_configuration() -> None:
    """Production must not couple short-lived proof tokens to access-token rotation."""
    if os.getenv("ENV", "development").strip().lower() != "production":
        return
    secret = os.getenv("FIDELITY_PROOF_SECRET_KEY", "")
    if len(secret.encode("utf-8")) < 32:
        raise RuntimeError("生产环境必须设置独立的 FIDELITY_PROOF_SECRET_KEY（至少 32 字节）")


def _value_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def create_fidelity_proof(
    *,
    resume_id: str,
    field_path: str,
    value: Any,
    fidelity_result: dict,
    evidence_references: list[str],
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "typ": "fidelity_proof",
        "resume_id": str(resume_id),
        "field_path": field_path,
        "value_hash": _value_hash(value),
        "fidelity_result": fidelity_result,
        "evidence_references": evidence_references,
        "iat": now,
        "exp": now + timedelta(minutes=30),
    }
    return jwt.encode(payload, _fidelity_proof_secret(), algorithm=ALGORITHM)


def verify_fidelity_proof(
    proof: str,
    *,
    resume_id: str,
    field_path: str,
    value: Any,
) -> dict:
    try:
        payload = jwt.decode(
            proof,
            _fidelity_proof_secret(),
            algorithms=[ALGORITHM],
        )
    except JWTError as exc:
        raise HTTPException(status_code=400, detail="忠实度凭证无效或已过期") from exc
    if (
        payload.get("typ") != "fidelity_proof"
        or str(payload.get("resume_id")) != str(resume_id)
        or payload.get("field_path") != field_path
        or payload.get("value_hash") != _value_hash(value)
    ):
        raise HTTPException(status_code=400, detail="忠实度凭证与补丁不一致")
    fidelity = payload.get("fidelity_result") or {}
    if fidelity.get("violated"):
        raise HTTPException(status_code=400, detail="补丁未通过忠实度校验")
    return payload
