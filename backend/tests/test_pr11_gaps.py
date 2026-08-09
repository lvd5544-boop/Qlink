"""PR11 gap-fill: virus scan, signed download, idempotency, ResumeVersion concurrency."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.career_vault import create_resume_version
from app.claim_passport import sync_resume_claims
from app.models_db import ApiIdempotencyKey
from app.object_storage import LocalVolumeAdapter, issue_download_token, verify_download_token
from app.virus_scan import EICAR_SIGNATURE, scan_bytes


async def _sync_one(db_session, resume, actor_id):
    claims = await sync_resume_claims(
        db_session, resume, actor_id=str(actor_id), reason="pr11_gap_test"
    )
    await db_session.commit()
    return claims[0]


def test_eicar_signature_is_rejected_by_scanner(monkeypatch):
    monkeypatch.setenv("VIRUS_SCAN_FAIL_MODE", "open")
    monkeypatch.delenv("CLAMAV_HOST", raising=False)
    clean = scan_bytes(b"harmless evidence text")
    assert clean.clean is True
    infected = scan_bytes(b"prefix " + EICAR_SIGNATURE + b" suffix")
    assert infected.clean is False
    assert infected.engine == "eicar_signature"


def test_scanner_is_fail_closed_when_clamav_is_not_configured(monkeypatch):
    monkeypatch.setenv("VIRUS_SCAN_FAIL_MODE", "closed")
    monkeypatch.delenv("CLAMAV_HOST", raising=False)
    result = scan_bytes(b"harmless evidence text")
    assert result.clean is False
    assert result.engine == "clamav"
    assert result.detail == "scanner_not_configured"


async def test_complete_upload_rejects_eicar_and_keeps_object_out(
    client, candidate_a, auth_header, tmp_path, monkeypatch
):
    monkeypatch.setenv("EVIDENCE_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    initialized = await client.post(
        "/evidence-vault/artifacts/init-upload",
        json={
            "artifact_type": "document",
            "title": "malware probe",
            "allowed_uses": ["resume_assistance"],
            "default_visibility": "private",
        },
        headers=auth_header(candidate_a),
    )
    assert initialized.status_code == 200, initialized.text
    artifact_id = initialized.json()["artifact"]["id"]

    rejected = await client.post(
        f"/evidence-vault/artifacts/{artifact_id}/complete-upload",
        files={"file": ("probe.txt", EICAR_SIGNATURE, "text/plain")},
        headers=auth_header(candidate_a),
    )
    assert rejected.status_code == 422
    detail = rejected.json()["detail"]
    assert detail["error"] == "malware_detected"

    stored = await client.get(
        f"/evidence-vault/artifacts/{artifact_id}",
        headers=auth_header(candidate_a),
    )
    assert stored.status_code == 200
    assert stored.json()["artifact"]["has_file"] is False
    assert stored.json()["artifact"]["content_hash"] is None


async def test_complete_upload_fails_closed_when_scanner_is_unavailable(
    client, candidate_a, auth_header, tmp_path, monkeypatch
):
    monkeypatch.setenv("EVIDENCE_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("VIRUS_SCAN_FAIL_MODE", "closed")
    monkeypatch.delenv("CLAMAV_HOST", raising=False)
    initialized = await client.post(
        "/evidence-vault/artifacts/init-upload",
        json={
            "artifact_type": "document",
            "title": "scanner outage probe",
            "allowed_uses": ["resume_assistance"],
            "default_visibility": "private",
        },
        headers=auth_header(candidate_a),
    )
    artifact_id = initialized.json()["artifact"]["id"]
    rejected = await client.post(
        f"/evidence-vault/artifacts/{artifact_id}/complete-upload",
        files={"file": ("safe.txt", b"harmless evidence", "text/plain")},
        headers=auth_header(candidate_a),
    )
    assert rejected.status_code == 503
    assert rejected.json()["detail"]["error"] == "scanner_unavailable"


async def test_signed_download_url_round_trip(
    client, candidate_a, candidate_b, auth_header, tmp_path, monkeypatch, db_session
):
    monkeypatch.setenv("EVIDENCE_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("SIGNED_URL_TTL_SECONDS", "120")

    initialized = await client.post(
        "/evidence-vault/artifacts/init-upload",
        json={
            "artifact_type": "document",
            "title": "safe evidence",
            "allowed_uses": ["resume_assistance"],
            "default_visibility": "private",
        },
        headers=auth_header(candidate_a),
    )
    artifact_id = initialized.json()["artifact"]["id"]
    payload = b"safe evidence bytes for signed download"
    uploaded = await client.post(
        f"/evidence-vault/artifacts/{artifact_id}/complete-upload",
        files={"file": ("safe.txt", payload, "text/plain")},
        headers=auth_header(candidate_a),
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["virus_scan"]["clean"] is True
    assert uploaded.json()["artifact"]["has_file"] is True

    from app.models_db import EvidenceArtifact

    artifact_row = await db_session.get(EvidenceArtifact, artifact_id)
    await db_session.refresh(artifact_row)
    object_ref = artifact_row.object_ref
    assert object_ref and object_ref.startswith("evidence/")

    url_resp = await client.get(
        f"/evidence-vault/artifacts/{artifact_id}/download-url",
        headers=auth_header(candidate_a),
    )
    assert url_resp.status_code == 200
    signed = url_resp.json()
    assert signed["backend"] == "local"
    assert "token=" in signed["url"]

    download_path = signed["url"]
    downloaded = await client.get(download_path)
    assert downloaded.status_code == 200
    assert downloaded.content == payload

    denied = await client.get(
        f"/evidence-vault/artifacts/{artifact_id}/download-url",
        headers=auth_header(candidate_b),
    )
    assert denied.status_code == 404

    storage = LocalVolumeAdapter(str(tmp_path / "vault"))
    assert storage.exists(object_ref)


async def test_idempotency_replay_and_conflict(client, candidate_a, auth_header, db_session):
    headers = {
        **auth_header(candidate_a),
        "Idempotency-Key": "pr11-experience-1",
    }
    body = {
        "experience_type": "project",
        "organization": "Idem Org",
        "title": "Idem Title",
        "date_precision": "unknown",
        "description": "idempotent create",
        "source_kind": "manual",
        "workflow_state": "active",
    }
    first = await client.post("/career-passport/experiences", json=body, headers=headers)
    assert first.status_code == 200, first.text
    experience_id = first.json()["experience"]["id"]

    replay = await client.post("/career-passport/experiences", json=body, headers=headers)
    assert replay.status_code == 200
    assert replay.json()["experience"]["id"] == experience_id

    row = (
        await db_session.execute(
            select(ApiIdempotencyKey).where(
                ApiIdempotencyKey.idempotency_key == "pr11-experience-1"
            )
        )
    ).scalar_one()
    assert row.scope == "career.experience.create"
    assert row.response_body["experience"]["id"] == experience_id

    conflict = await client.post(
        "/career-passport/experiences",
        json={**body, "title": "Different title"},
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["error"] == "idempotency_conflict"


async def test_upload_idempotency_fingerprints_file_bytes(
    client, candidate_a, auth_header, tmp_path, monkeypatch
):
    monkeypatch.setenv("EVIDENCE_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    initialized = await client.post(
        "/evidence-vault/artifacts/init-upload",
        json={
            "artifact_type": "document",
            "title": "idempotent upload",
            "allowed_uses": ["resume_assistance"],
            "default_visibility": "private",
        },
        headers=auth_header(candidate_a),
    )
    artifact_id = initialized.json()["artifact"]["id"]
    headers = {**auth_header(candidate_a), "Idempotency-Key": "same-upload-key"}
    first = await client.post(
        f"/evidence-vault/artifacts/{artifact_id}/complete-upload",
        files={"file": ("same.txt", b"first payload", "text/plain")},
        headers=headers,
    )
    assert first.status_code == 200
    conflict = await client.post(
        f"/evidence-vault/artifacts/{artifact_id}/complete-upload",
        files={"file": ("same.txt", b"other payload", "text/plain")},
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["error"] == "idempotency_conflict"


async def test_resume_version_numbers_increment_and_conflict_maps_to_409(
    client, db_session, resume_a, candidate_a, auth_header
):
    await _sync_one(db_session, resume_a, candidate_a.id)
    first = await client.post(
        f"/career-passport/resumes/{resume_a.id}/versions",
        json={"created_reason": "manual_edit"},
        headers=auth_header(candidate_a),
    )
    second = await client.post(
        f"/career-passport/resumes/{resume_a.id}/versions",
        json={"created_reason": "manual_edit"},
        headers=auth_header(candidate_a),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["version"]["version_number"] == 1
    assert second.json()["version"]["version_number"] == 2

    original_flush = db_session.flush

    async def boom(*_args, **_kwargs):
        raise IntegrityError("INSERT", {}, Exception("uq_resume_version_number"))

    db_session.flush = boom  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError, match="resume_version_conflict"):
            await create_resume_version(
                db_session,
                resume_a,
                user_id=str(candidate_a.id),
                reason="manual_edit",
                actor_id=str(candidate_a.id),
            )
    finally:
        db_session.flush = original_flush  # type: ignore[method-assign]
        await db_session.rollback()


async def test_resume_version_pg_advisory_lock_used_on_postgres(db_session, resume_a, candidate_a):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("advisory lock gate is PostgreSQL-only")

    calls: list[str] = []
    original_execute = db_session.execute

    async def tracking_execute(statement, *args, **kwargs):
        sql = str(statement)
        if "pg_advisory_xact_lock" in sql:
            calls.append(sql)
        return await original_execute(statement, *args, **kwargs)

    db_session.execute = tracking_execute  # type: ignore[method-assign]
    try:
        version = await create_resume_version(
            db_session,
            resume_a,
            user_id=str(candidate_a.id),
            reason="manual_edit",
            actor_id=str(candidate_a.id),
        )
        await db_session.commit()
        assert version.version_number >= 1
        assert calls, "expected pg_advisory_xact_lock during version allocation"
    finally:
        db_session.execute = original_execute  # type: ignore[method-assign]


@pytest.mark.postgresql
async def test_concurrent_resume_versions_are_unique_and_contiguous(
    test_engine, db_session, resume_a, candidate_a
):
    await _sync_one(db_session, resume_a, candidate_a.id)
    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def create_one() -> int:
        async with session_factory() as session:
            owned_resume = await session.get(type(resume_a), str(resume_a.id))
            version = await create_resume_version(
                session,
                owned_resume,
                user_id=str(candidate_a.id),
                reason="concurrent_acceptance",
                actor_id=str(candidate_a.id),
            )
            await session.commit()
            return int(version.version_number)

    numbers = await asyncio.gather(*(create_one() for _ in range(8)))
    assert sorted(numbers) == list(range(1, 9))


def test_download_token_rejects_tamper():
    signed = issue_download_token(
        artifact_id="art-1",
        user_id="user-1",
        object_ref="evidence/user-1/art-1/file.txt",
    )
    token = signed.url.split("token=", 1)[1]
    with pytest.raises(PermissionError):
        verify_download_token(
            token=token + "x",
            artifact_id="art-1",
            user_id="user-1",
            object_ref="evidence/user-1/art-1/file.txt",
        )
