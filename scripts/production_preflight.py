#!/usr/bin/env python3
"""Fail-closed validation for a QLink production environment file."""

from __future__ import annotations

import argparse
import re
import stat
from pathlib import Path
from urllib.parse import urlparse

PLACEHOLDER_MARKERS = ("change_me", "changeme", "example-secret", "replace_me")
DOMAIN_PATTERN = re.compile(
    r"^(?=.{4,253}$)(?!-)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
LOG_SIZE_PATTERN = re.compile(r"^[1-9][0-9]{0,3}[kKmMgG]$")


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            raise ValueError(f"line {number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError(f"line {number}: invalid variable name")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def validate(
    path: Path, env: dict[str, str], *, go_live: bool = False
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        errors.append(
            "environment file must not be readable or writable by group/others; run chmod 600"
        )

    domain = env.get("PUBLIC_DOMAIN", "").strip().lower()
    if not DOMAIN_PATTERN.fullmatch(domain) or domain.endswith(".example.com"):
        errors.append(
            "PUBLIC_DOMAIN must be a real DNS hostname, without scheme, path, localhost, or placeholder domain"
        )

    origin = urlparse(env.get("PUBLIC_ORIGIN", ""))
    if (
        origin.scheme != "https"
        or origin.hostname != domain
        or origin.path not in {"", "/"}
        or origin.params
        or origin.query
        or origin.fragment
        or origin.port not in {None, 443}
    ):
        errors.append(
            "PUBLIC_ORIGIN must be exactly https://PUBLIC_DOMAIN (optional port 443 only)"
        )

    if not EMAIL_PATTERN.fullmatch(env.get("ACME_EMAIL", "")):
        errors.append("ACME_EMAIL must be a valid operator email")

    legal_entity = env.get("LEGAL_ENTITY_NAME", "").strip()
    if len(legal_entity) < 2 or any(
        marker in legal_entity.lower()
        for marker in (*PLACEHOLDER_MARKERS, "pilot operator")
    ):
        errors.append("LEGAL_ENTITY_NAME must identify the accountable pilot operator")
    for key in ("SUPPORT_EMAIL", "PRIVACY_CONTACT_EMAIL", "INCIDENT_CONTACT_EMAIL"):
        value = env.get(key, "").strip().lower()
        if not EMAIL_PATTERN.fullmatch(value) or value.endswith(
            ("@example.com", ".invalid")
        ):
            errors.append(f"{key} must be a real monitored contact address")

    if env.get("APP_BIND_ADDRESS", "127.0.0.1") not in {"127.0.0.1", "::1"}:
        errors.append(
            "APP_BIND_ADDRESS must be loopback; only the HTTPS edge may be public"
        )

    secret_requirements = {
        "POSTGRES_PASSWORD": 24,
        "SECRET_KEY": 32,
        "FIDELITY_PROOF_SECRET_KEY": 32,
        "EVIDENCE_DOWNLOAD_SIGNING_KEY": 32,
        "EMPLOYER_INVITE_CODE": 16,
    }
    observed_secrets: list[str] = []
    for key, minimum in secret_requirements.items():
        value = env.get(key, "")
        lowered = value.lower()
        if len(value) < minimum or any(
            marker in lowered for marker in PLACEHOLDER_MARKERS
        ):
            errors.append(
                f"{key} must be a non-placeholder random value of at least {minimum} characters"
            )
        elif value in observed_secrets:
            errors.append(f"{key} must not reuse another production secret")
        observed_secrets.append(value)

    try:
        expiry = int(env.get("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
        if not 5 <= expiry <= 480:
            errors.append("ACCESS_TOKEN_EXPIRE_MINUTES must be between 5 and 480")
    except ValueError:
        errors.append("ACCESS_TOKEN_EXPIRE_MINUTES must be an integer")

    if not enabled(env.get("AUTH_COOKIE_SECURE")):
        errors.append("AUTH_COOKIE_SECURE must be true in production")
    if env.get("AUTH_COOKIE_SAMESITE", "lax").strip().lower() not in {"lax", "strict"}:
        errors.append("AUTH_COOKIE_SAMESITE must be lax or strict in production")

    try:
        upload_max = int(env.get("UPLOAD_MAX_BYTES", str(5 * 1024 * 1024)))
        if not 1024 <= upload_max <= 5 * 1024 * 1024:
            errors.append(
                "UPLOAD_MAX_BYTES must be between 1024 and 5242880 so it stays within the production proxy limit"
            )
    except ValueError:
        errors.append("UPLOAD_MAX_BYTES must be an integer")

    log_size = env.get("LOG_MAX_SIZE", "10m").strip()
    if not LOG_SIZE_PATTERN.fullmatch(log_size):
        errors.append("LOG_MAX_SIZE must be a positive Docker size such as 10m")
    try:
        log_files = int(env.get("LOG_MAX_FILES", "5"))
        if not 1 <= log_files <= 20:
            errors.append("LOG_MAX_FILES must be between 1 and 20")
    except ValueError:
        errors.append("LOG_MAX_FILES must be an integer")

    if enabled(env.get("AI_AUDIT_CONTENT_LOGGING")):
        errors.append(
            "AI_AUDIT_CONTENT_LOGGING must remain false for real-user deployment"
        )
    if not enabled(env.get("VIRUS_SCAN_ENABLED")):
        errors.append("VIRUS_SCAN_ENABLED must be true")
    if env.get("VIRUS_SCAN_FAIL_MODE", "").lower() != "closed":
        errors.append("VIRUS_SCAN_FAIL_MODE must be closed")

    ai_enabled = enabled(env.get("AI_ENABLED"))
    model_required = enabled(env.get("MODEL_REQUIRED"))
    if model_required and not ai_enabled:
        errors.append("MODEL_REQUIRED=true requires AI_ENABLED=true")
    if model_required and not (
        env.get("AI_PRIMARY_API_KEY") or env.get("DEEPSEEK_API_KEY")
    ):
        errors.append("MODEL_REQUIRED=true requires a configured model provider key")

    storage = env.get("OBJECT_STORAGE_BACKEND", "local").lower()
    if storage not in {"local", "s3", "minio"}:
        errors.append("OBJECT_STORAGE_BACKEND must be local, s3, or minio")
    elif storage == "local":
        warnings.append(
            "local Evidence Vault selected: encrypted off-host volume backups are mandatory"
        )
    else:
        for key in ("S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
            if not env.get(key):
                errors.append(f"{key} is required for {storage} object storage")
        if storage == "minio" and not env.get("S3_ENDPOINT"):
            errors.append("S3_ENDPOINT is required for minio")

    smtp_keys = ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM")
    configured_smtp = [key for key in smtp_keys if env.get(key)]
    if configured_smtp and len(configured_smtp) != len(smtp_keys):
        missing = ", ".join(key for key in smtp_keys if not env.get(key))
        errors.append(f"partial SMTP configuration; missing: {missing}")
    elif not configured_smtp:
        message = "SMTP is not configured: password recovery and operational email are unavailable"
        if go_live:
            errors.append(message)
        else:
            warnings.append(message)
    if configured_smtp and not enabled(env.get("SMTP_START_TLS", "true")):
        errors.append("SMTP_START_TLS must be true in production")

    if go_live:
        confirmations = {
            "OFFSITE_BACKUP_CONFIRMED": "encrypted off-host backup destination",
            "RESTORE_REHEARSAL_CONFIRMED": "synthetic database/uploads/Evidence Vault restore rehearsal",
            "MONITORING_ALERTS_CONFIRMED": "availability, security, and disk-space alert delivery",
            "LEGAL_REVIEW_CONFIRMED": "jurisdiction-specific notices, processors, and retention review",
        }
        for key, description in confirmations.items():
            if not enabled(env.get(key)):
                errors.append(f"{key} must be true after verifying {description}")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument(
        "--go-live",
        action="store_true",
        help="also enforce external controls required before inviting real users",
    )
    args = parser.parse_args()
    path = args.env_file.expanduser().resolve()
    if not path.is_file():
        print(f"ERROR: environment file does not exist: {path}")
        return 2
    try:
        env = load_env(path)
        errors, warnings = validate(path, env, go_live=args.go_live)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"Production preflight failed with {len(errors)} error(s).")
        return 1
    if args.go_live:
        print(
            "Go-live preflight passed; required external controls were explicitly confirmed."
        )
    else:
        print("Production preflight passed; no secret values were printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
