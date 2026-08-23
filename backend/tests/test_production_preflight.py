from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = spec_from_file_location("production_preflight", ROOT / "scripts" / "production_preflight.py")
assert SPEC and SPEC.loader
preflight = module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def valid_environment() -> dict[str, str]:
    return {
        "PUBLIC_DOMAIN": "jobs.qlink.cn",
        "PUBLIC_ORIGIN": "https://jobs.qlink.cn",
        "ACME_EMAIL": "operator@qlink.cn",
        "LEGAL_ENTITY_NAME": "QLink Shanghai Pilot Team",
        "SUPPORT_EMAIL": "support@qlink.cn",
        "PRIVACY_CONTACT_EMAIL": "privacy@qlink.cn",
        "INCIDENT_CONTACT_EMAIL": "incident@qlink.cn",
        "APP_BIND_ADDRESS": "127.0.0.1",
        "POSTGRES_PASSWORD": "database-" + "a" * 32,
        "SECRET_KEY": "access-" + "b" * 40,
        "FIDELITY_PROOF_SECRET_KEY": "proof-" + "c" * 40,
        "EVIDENCE_DOWNLOAD_SIGNING_KEY": "download-" + "d" * 40,
        "EMPLOYER_INVITE_CODE": "invite-" + "e" * 24,
        "ACCESS_TOKEN_EXPIRE_MINUTES": "120",
        "AUTH_COOKIE_SECURE": "true",
        "AUTH_COOKIE_SAMESITE": "lax",
        "UPLOAD_MAX_BYTES": "5242880",
        "LOG_MAX_SIZE": "10m",
        "LOG_MAX_FILES": "5",
        "AI_ENABLED": "false",
        "MODEL_REQUIRED": "false",
        "AI_AUDIT_CONTENT_LOGGING": "false",
        "VIRUS_SCAN_ENABLED": "true",
        "VIRUS_SCAN_FAIL_MODE": "closed",
        "OBJECT_STORAGE_BACKEND": "local",
    }


def private_env_file(tmp_path: Path) -> Path:
    path = tmp_path / ".env.production"
    path.write_text("placeholder\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def test_valid_pilot_environment_passes_with_explicit_local_backup_warning(tmp_path):
    errors, warnings = preflight.validate(private_env_file(tmp_path), valid_environment())

    assert errors == []
    assert any("off-host" in warning for warning in warnings)
    assert any("SMTP" in warning for warning in warnings)


def test_preflight_rejects_public_app_port_weak_reused_secrets_and_unsafe_scanning(tmp_path):
    env = valid_environment()
    env.update(
        {
            "PUBLIC_DOMAIN": "jobs.example.com",
            "PUBLIC_ORIGIN": "http://jobs.example.com",
            "APP_BIND_ADDRESS": "0.0.0.0",
            "SECRET_KEY": "CHANGE_ME",
            "FIDELITY_PROOF_SECRET_KEY": "CHANGE_ME",
            "VIRUS_SCAN_ENABLED": "false",
            "VIRUS_SCAN_FAIL_MODE": "open",
            "AI_AUDIT_CONTENT_LOGGING": "true",
        }
    )

    errors, _ = preflight.validate(private_env_file(tmp_path), env)
    combined = "\n".join(errors)

    assert "PUBLIC_DOMAIN" in combined
    assert "PUBLIC_ORIGIN" in combined
    assert "APP_BIND_ADDRESS" in combined
    assert "SECRET_KEY" in combined
    assert "VIRUS_SCAN_ENABLED" in combined
    assert "VIRUS_SCAN_FAIL_MODE" in combined
    assert "AI_AUDIT_CONTENT_LOGGING" in combined


def test_required_model_and_object_storage_must_be_fully_configured(tmp_path):
    env = valid_environment()
    env.update(
        {
            "AI_ENABLED": "true",
            "MODEL_REQUIRED": "true",
            "OBJECT_STORAGE_BACKEND": "minio",
        }
    )

    errors, _ = preflight.validate(private_env_file(tmp_path), env)
    combined = "\n".join(errors)

    assert "model provider key" in combined
    assert "S3_BUCKET" in combined
    assert "S3_ACCESS_KEY" in combined
    assert "S3_SECRET_KEY" in combined
    assert "S3_ENDPOINT" in combined


def test_partial_or_unencrypted_smtp_is_rejected(tmp_path):
    env = valid_environment()
    env.update({"SMTP_HOST": "smtp.example.com", "SMTP_START_TLS": "false"})

    errors, _ = preflight.validate(private_env_file(tmp_path), env)
    combined = "\n".join(errors)

    assert "partial SMTP" in combined
    assert "SMTP_START_TLS" in combined


def test_browser_session_cookie_must_be_secure_and_same_site(tmp_path):
    env = valid_environment()
    env.update({"AUTH_COOKIE_SECURE": "false", "AUTH_COOKIE_SAMESITE": "none"})

    errors, _ = preflight.validate(private_env_file(tmp_path), env)
    combined = "\n".join(errors)

    assert "AUTH_COOKIE_SECURE" in combined
    assert "AUTH_COOKIE_SAMESITE" in combined


def test_upload_proxy_contract_and_log_rotation_are_bounded(tmp_path):
    env = valid_environment()
    env.update(
        {
            "UPLOAD_MAX_BYTES": "6291456",
            "LOG_MAX_SIZE": "unlimited",
            "LOG_MAX_FILES": "0",
        }
    )

    errors, _ = preflight.validate(private_env_file(tmp_path), env)
    combined = "\n".join(errors)

    assert "UPLOAD_MAX_BYTES" in combined
    assert "LOG_MAX_SIZE" in combined
    assert "LOG_MAX_FILES" in combined


def test_production_assets_keep_uploads_usable_and_logs_rotated():
    nginx = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    base_compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "client_max_body_size 6m;" in nginx
    assert "UPLOAD_MAX_BYTES: ${UPLOAD_MAX_BYTES:-5242880}" in base_compose
    assert 'max-size: "${LOG_MAX_SIZE:-10m}"' in compose
    assert 'max-file: "${LOG_MAX_FILES:-5}"' in compose


def test_environment_file_permissions_fail_closed(tmp_path):
    path = private_env_file(tmp_path)
    path.chmod(0o644)

    errors, _ = preflight.validate(path, valid_environment())

    assert any("chmod 600" in error for error in errors)


def test_public_operator_identity_and_contacts_are_required(tmp_path):
    env = valid_environment()
    env.update(
        {
            "LEGAL_ENTITY_NAME": "CHANGE_ME_LEGAL_OPERATOR",
            "SUPPORT_EMAIL": "support@example.com",
            "PRIVACY_CONTACT_EMAIL": "privacy@example.invalid",
            "INCIDENT_CONTACT_EMAIL": "incident@example.com",
        }
    )

    errors, _ = preflight.validate(private_env_file(tmp_path), env)
    combined = "\n".join(errors)

    assert "LEGAL_ENTITY_NAME" in combined
    assert "SUPPORT_EMAIL" in combined
    assert "PRIVACY_CONTACT_EMAIL" in combined
    assert "INCIDENT_CONTACT_EMAIL" in combined


def test_go_live_requires_recovery_and_explicit_external_control_evidence(tmp_path):
    env = valid_environment()

    errors, warnings = preflight.validate(private_env_file(tmp_path), env, go_live=True)
    combined = "\n".join(errors)

    assert "SMTP is not configured" in combined
    assert "OFFSITE_BACKUP_CONFIRMED" in combined
    assert "RESTORE_REHEARSAL_CONFIRMED" in combined
    assert "MONITORING_ALERTS_CONFIRMED" in combined
    assert "LEGAL_REVIEW_CONFIRMED" in combined
    assert not any("SMTP is not configured" in warning for warning in warnings)


def test_go_live_passes_only_after_external_controls_are_confirmed(tmp_path):
    env = valid_environment()
    env.update(
        {
            "SMTP_HOST": "smtp.qlink.cn",
            "SMTP_USERNAME": "mailer@qlink.cn",
            "SMTP_PASSWORD": "smtp-secret-for-test",
            "SMTP_FROM": "mailer@qlink.cn",
            "SMTP_START_TLS": "true",
            "OFFSITE_BACKUP_CONFIRMED": "true",
            "RESTORE_REHEARSAL_CONFIRMED": "true",
            "MONITORING_ALERTS_CONFIRMED": "true",
            "LEGAL_REVIEW_CONFIRMED": "true",
        }
    )

    errors, _ = preflight.validate(private_env_file(tmp_path), env, go_live=True)

    assert errors == []
