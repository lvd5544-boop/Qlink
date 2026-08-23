from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import func, select

from app.models import JobInfo, ResumeInfo
from app.models_db import (
    ApplicationMessage,
    AuditFindingFeedback,
    ClaimEvent,
    CredibilityAuditRecord,
    InterviewInvitation,
    JobApplication,
    JobDescription,
    MatchResult,
    Resume,
    ResumeClaim,
    ResumeSuggestion,
    ResumeVariant,
    UsageEvent,
    User,
)
from app.auth_routes import _login_attempts
from app.claim_passport import sync_resume_claims
from app.main import resolve_cors_origins


pytestmark = pytest.mark.asyncio


async def test_sensitive_pr4_route_inventory_rejects_anonymous(
    client, candidate_a, resume_a, employer_a, job_a
):
    requests = [
        ("GET", "/jobs/mine", None),
        ("GET", f"/jobs/{employer_a.id}", None),
        ("PUT", f"/jobs/{job_a.id}", {"parsed_json": {}}),
        ("DELETE", f"/jobs/{job_a.id}", None),
        ("POST", "/jobs/sync-sources", None),
        ("POST", "/match", None),
        ("POST", f"/match/user/{candidate_a.id}", None),
        ("GET", f"/matches/user/{candidate_a.id}", None),
        ("GET", f"/matches/resume/{resume_a.id}", None),
        ("GET", f"/matches/job/{job_a.id}", None),
        ("POST", "/analytics/rebuild", None),
        ("POST", "/analytics/sync-forum-insights", None),
    ]
    for method, path, payload in requests:
        response = await client.request(method, path, json=payload)
        assert response.status_code == 401, (method, path, response.text)


async def test_post_job_requires_current_employer(client, auth_header, candidate_a):
    anonymous = await client.post("/post-job", params={"description_text": "Python"})
    candidate = await client.post(
        "/post-job",
        headers=auth_header(candidate_a),
        params={"description_text": "Python"},
    )
    assert anonymous.status_code == 401
    assert candidate.status_code == 403


async def test_post_job_ignores_spoofed_employer_id(
    client, auth_header, employer_a, employer_b, monkeypatch
):
    monkeypatch.setattr(
        "app.main.parse_job_with_llm",
        lambda text: JobInfo(title="安全岗位", requirements=text),
    )
    response = await client.post(
        f"/post-job?employer_id={employer_b.id}",
        headers=auth_header(employer_a),
        params={"description_text": "Python and PostgreSQL"},
    )
    assert response.status_code == 200

    mine = await client.get("/jobs/mine", headers=auth_header(employer_a))
    other = await client.get("/jobs/mine", headers=auth_header(employer_b))
    assert [row["title"] for row in mine.json()] == ["安全岗位"]
    assert other.json() == []


async def test_job_owner_and_admin_boundaries(
    client, auth_header, candidate_a, employer_a, employer_b, admin_user, job_a, monkeypatch
):
    denied_list = await client.get(f"/jobs/{employer_a.id}", headers=auth_header(employer_b))
    denied_update = await client.put(
        f"/jobs/{job_a.id}",
        headers=auth_header(employer_b),
        json={"parsed_json": {"title": "stolen"}},
    )
    denied_delete = await client.delete(f"/jobs/{job_a.id}", headers=auth_header(employer_b))
    assert denied_list.status_code in {403, 404}
    assert denied_update.status_code in {403, 404}
    assert denied_delete.status_code in {403, 404}

    for path in ("/jobs/sync-sources", "/analytics/rebuild", "/analytics/sync-forum-insights"):
        denied = await client.post(path, headers=auth_header(candidate_a))
        assert denied.status_code == 403

    async def fake_enqueue(*_args, **_kwargs):
        return {
            "job_id": "job-sync-1",
            "status": "queued",
            "inline": False,
            "message_id": "1-0",
        }

    monkeypatch.setattr("app.main.enqueue_job", fake_enqueue)
    # Admin dependency must be reached; long scrape/rebuild runs in the worker.
    admin = await client.post("/jobs/sync-sources", headers=auth_header(admin_user))
    assert admin.status_code == 200
    assert admin.json()["job_id"] == "job-sync-1"
    assert admin.json()["status"] == "queued"


async def test_match_routes_enforce_resource_ownership(
    client,
    auth_header,
    candidate_a,
    candidate_b,
    employer_a,
    employer_b,
    resume_a,
    resume_b,
    job_a,
    match_a,
):
    assert (
        await client.get(f"/matches/user/{candidate_a.id}", headers=auth_header(candidate_b))
    ).status_code in {403, 404}
    assert (
        await client.get(f"/matches/resume/{resume_a.id}", headers=auth_header(candidate_b))
    ).status_code in {403, 404}
    assert (
        await client.get(f"/matches/job/{job_a.id}", headers=auth_header(employer_b))
    ).status_code in {403, 404}
    targeted = await client.post(
        "/match",
        headers=auth_header(employer_a),
        params={"job_id": str(job_a.id), "resume_id": str(resume_b.id)},
    )
    assert targeted.status_code == 400

    own_candidate = await client.get(
        f"/matches/resume/{resume_a.id}", headers=auth_header(candidate_a)
    )
    own_employer = await client.get(f"/matches/job/{job_a.id}", headers=auth_header(employer_a))
    assert own_candidate.status_code == 200
    assert own_employer.status_code == 200


async def test_match_result_alone_does_not_authorize_resume_detail(
    client, auth_header, db_session, employer_a, job_a, resume_a, resume_b, application_a
):
    db_session.add(
        MatchResult(
            resume_id=str(resume_b.id),
            job_id=str(job_a.id),
            score=8.0,
            reason="match only is not consent",
            score_breakdown={},
        )
    )
    await db_session.commit()

    match_only = await client.get(f"/resume/{resume_b.id}", headers=auth_header(employer_a))
    authorized_application = await client.get(
        f"/resume/{resume_a.id}", headers=auth_header(employer_a)
    )
    assert match_only.status_code == 404
    assert authorized_application.status_code == 200


async def test_match_result_alone_does_not_expose_candidate_in_job_matches(
    client, auth_header, db_session, employer_a, job_a, resume_b
):
    db_session.add(
        MatchResult(
            resume_id=str(resume_b.id),
            job_id=str(job_a.id),
            score=8.0,
            reason="automatic match without candidate consent",
            score_breakdown={"private_signal": "must-not-leak"},
        )
    )
    await db_session.commit()

    response = await client.get(f"/matches/job/{job_a.id}", headers=auth_header(employer_a))

    assert response.status_code == 200
    serialized = response.json()
    assert serialized == []
    assert "Candidate B" not in response.text
    assert str(resume_b.id) not in response.text
    assert "private_signal" not in response.text


async def test_public_job_payload_redacts_contact_and_internal_text(client, db_session, job_a):
    job_a.raw_text = "internal source document"
    job_a.parsed_json = {
        **(job_a.parsed_json or {}),
        "company_name": "Example",
        "contact_person": "Private HR",
        "contact_info": "private@example.test",
        "internal_notes": "do not expose",
    }
    await db_session.commit()

    listing = await client.get("/browse-jobs")
    detail = await client.get(f"/job/{job_a.id}")
    assert listing.status_code == 200
    assert detail.status_code == 200
    serialized = f"{listing.json()} {detail.json()}"
    assert "private@example.test" not in serialized
    assert "Private HR" not in serialized
    assert "internal source document" not in serialized
    assert "do not expose" not in serialized


async def test_public_registration_cannot_choose_privileged_role(client):
    weak = await client.post(
        "/auth/register",
        json={"email": "weak@test.local", "password": "short", "role": "candidate"},
    )
    employer = await client.post(
        "/auth/register",
        json={
            "email": "employer-self@test.local",
            "password": "StrongPass-123",
            "role": "employer",
        },
    )
    admin = await client.post(
        "/auth/register",
        json={
            "email": "admin-self@test.local",
            "password": "StrongPass-123",
            "role": "admin",
        },
    )
    assert weak.status_code in {400, 422}
    assert employer.status_code == 403
    assert admin.status_code == 403


async def test_candidate_registration_provisions_free_subscription(
    client,
    db_session,
    billing_catalog,
):
    response = await client.post(
        "/auth/register",
        json={
            "email": "new-candidate@test.local",
            "password": "StrongPass-123",
            "role": "candidate",
            "terms_accepted": True,
            "privacy_notice_acknowledged": True,
        },
    )
    assert response.status_code == 200, response.text
    from app.models_db import User, UserSubscription

    registered = (
        await db_session.execute(select(User).where(User.email == "new-candidate@test.local"))
    ).scalar_one()
    subscription = (
        await db_session.execute(
            select(UserSubscription).where(UserSubscription.user_id == str(registered.id))
        )
    ).scalar_one()
    assert subscription.plan_code == "candidate-free-v1"
    assert subscription.status == "active"


@pytest.mark.parametrize(
    "password",
    [
        "Password123",
        "Qwerty12345",
        "Admin123456",
    ],
)
async def test_public_registration_rejects_common_weak_passwords(client, password):
    response = await client.post(
        "/auth/register",
        json={
            "email": f"weak-{password.lower()}@test.local",
            "password": password,
            "role": "candidate",
        },
    )
    assert response.status_code == 422


async def test_employer_registration_requires_server_invite(
    client, db_session, billing_catalog, monkeypatch
):
    monkeypatch.setenv("EMPLOYER_INVITE_CODE", "invite-only-secret")
    denied = await client.post(
        "/auth/register-employer",
        json={
            "email": "new-employer@test.local",
            "password": "StrongPass-123",
            "invite_code": "wrong",
        },
    )
    allowed = await client.post(
        "/auth/register-employer",
        json={
            "email": "new-employer@test.local",
            "password": "StrongPass-123",
            "invite_code": "invite-only-secret",
            "terms_accepted": True,
            "privacy_notice_acknowledged": True,
        },
    )
    assert denied.status_code == 403
    assert allowed.status_code == 200
    from app.models_db import (
        OrganizationMembership,
        OrganizationSubscription,
        User,
    )

    registered = (
        await db_session.execute(select(User).where(User.email == "new-employer@test.local"))
    ).scalar_one()
    membership = (
        await db_session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == str(registered.id)
            )
        )
    ).scalar_one()
    subscription = (
        await db_session.execute(
            select(OrganizationSubscription).where(
                OrganizationSubscription.organization_id == membership.organization_id
            )
        )
    ).scalar_one()
    assert membership.role == "owner"
    assert subscription.plan_code == "organization-seat-v1"
    assert subscription.seat_quantity == 1


async def test_logout_revokes_access_token(client, candidate_a):
    login = await client.post(
        "/auth/login",
        json={"email": candidate_a.email, "password": "test-pass-123"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/usage/me", headers=headers)).status_code == 200
    assert (await client.post("/auth/logout", headers=headers)).status_code == 200
    assert (await client.get("/usage/me", headers=headers)).status_code == 401


async def test_login_rate_limit_blocks_repeated_failures(client, monkeypatch):
    _login_attempts.clear()
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "2")
    payload = {"email": "missing@test.local", "password": "WrongPass-123"}
    first = await client.post("/auth/login", json=payload)
    second = await client.post("/auth/login", json=payload)
    blocked = await client.post("/auth/login", json=payload)
    assert first.status_code == 401
    assert second.status_code == 401
    assert blocked.status_code == 429
    _login_attempts.clear()


async def test_production_cors_requires_explicit_allowlist(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError):
        resolve_cors_origins()
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.test")
    assert resolve_cors_origins() == ["https://app.example.test"]


@pytest.mark.parametrize(
    ("environment", "secret"),
    [
        ("production", ""),
        ("Production", "dev-secret-key-change-in-production"),
        (" production ", "short-secret"),
    ],
)
async def test_production_rejects_empty_default_or_weak_jwt_secret(environment, secret, tmp_path):
    backend_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        {
            "ENV": environment,
            "SECRET_KEY": secret,
            "CORS_ORIGINS": "https://app.example.test",
            "TESTING": "1",
            "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path / 'config.db'}",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.main import app",
        ],
        cwd=backend_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode != 0
    combined = f"{result.stdout}\n{result.stderr}"
    assert "生产环境必须设置高强度 SECRET_KEY" in combined


async def test_resume_upload_rejects_path_traversal_and_cleans_temp_files(
    client, auth_header, candidate_a, monkeypatch, tmp_path
):
    monkeypatch.setattr("app.main.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(
        "app.main.parse_with_llm",
        lambda text: ResumeInfo(name="Safe Candidate", summary=text),
    )
    response = await client.post(
        "/parse-resume",
        headers=auth_header(candidate_a),
        files={
            "file": (
                "../../escape.txt",
                BytesIO(b"plain text resume"),
                "text/plain",
            )
        },
    )
    assert response.status_code == 200
    assert list(tmp_path.iterdir()) == []
    assert not (tmp_path.parent / "escape.txt").exists()


async def test_resume_upload_rejects_oversized_or_mismatched_content(
    client, auth_header, candidate_a, monkeypatch, tmp_path
):
    monkeypatch.setattr("app.main.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("UPLOAD_MAX_BYTES", "32")
    oversized = await client.post(
        "/parse-resume",
        headers=auth_header(candidate_a),
        files={"file": ("resume.txt", b"x" * 64, "text/plain")},
    )
    mismatched = await client.post(
        "/parse-resume",
        headers=auth_header(candidate_a),
        files={"file": ("resume.pdf", b"not-a-pdf", "application/pdf")},
    )
    assert oversized.status_code == 413
    assert mismatched.status_code in {400, 415, 422}
    assert list(tmp_path.iterdir()) == []


async def test_upload_parser_error_is_redacted_and_temp_file_is_removed(
    client, auth_header, candidate_a, monkeypatch, tmp_path
):
    monkeypatch.setattr("app.main.UPLOAD_DIR", str(tmp_path))

    def fail_parser(_text):
        raise RuntimeError("/private/internal/path api-key=secret")

    monkeypatch.setattr("app.main.parse_with_llm", fail_parser)
    response = await client.post(
        "/parse-resume",
        headers=auth_header(candidate_a),
        files={"file": ("resume.txt", b"plain text resume", "text/plain")},
    )
    assert response.status_code == 502
    assert "private/internal" not in response.text
    assert "api-key" not in response.text
    assert list(tmp_path.iterdir()) == []


async def test_resume_delete_cascades_private_dependents_transactionally(
    client, auth_header, db_session, candidate_a, employer_a, resume_a, job_a, application_a
):
    suggestion = ResumeSuggestion(
        resume_id=str(resume_a.id),
        source="health_check",
        suggestion_key="pr4-delete",
        title="delete me",
        status="pending",
    )
    variant = ResumeVariant(
        resume_id=str(resume_a.id),
        variant_key="pr4-delete",
        label="delete me",
        parsed_json={"name": "variant"},
        job_id=str(job_a.id),
    )
    match = MatchResult(
        resume_id=str(resume_a.id),
        job_id=str(job_a.id),
        score=6,
        reason="delete me",
    )
    invitation = InterviewInvitation(
        job_id=str(job_a.id),
        employer_id=str(employer_a.id),
        candidate_id=str(candidate_a.id),
        resume_id=str(resume_a.id),
        application_id=str(application_a.id),
        status="pending",
    )
    message = ApplicationMessage(
        application_id=str(application_a.id),
        sender_id=str(candidate_a.id),
        body="delete me",
    )
    audit = CredibilityAuditRecord(
        employer_id=str(employer_a.id),
        job_id=str(job_a.id),
        resume_id=str(resume_a.id),
        application_id=str(application_a.id),
        report={},
    )
    db_session.add_all([suggestion, variant, match, invitation, message, audit])
    await db_session.flush()
    feedback = AuditFindingFeedback(
        audit_record_id=str(audit.id),
        employer_id=str(employer_a.id),
        application_id=str(application_a.id),
        finding_id="delete",
        label="useful",
    )
    db_session.add(feedback)
    await db_session.commit()

    response = await client.delete(f"/resumes/{resume_a.id}", headers=auth_header(candidate_a))
    assert response.status_code == 200

    for model in (
        Resume,
        ResumeSuggestion,
        ResumeVariant,
        MatchResult,
        JobApplication,
        InterviewInvitation,
        ApplicationMessage,
        CredibilityAuditRecord,
        AuditFindingFeedback,
    ):
        count = (await db_session.execute(select(func.count()).select_from(model))).scalar_one()
        assert count == 0, model.__name__


async def test_job_delete_cascades_private_dependents_transactionally(
    client, auth_header, db_session, candidate_a, employer_a, resume_a, job_a, application_a
):
    db_session.add_all(
        [
            MatchResult(
                resume_id=str(resume_a.id),
                job_id=str(job_a.id),
                score=5,
                reason="delete with job",
            ),
            InterviewInvitation(
                job_id=str(job_a.id),
                employer_id=str(employer_a.id),
                candidate_id=str(candidate_a.id),
                resume_id=str(resume_a.id),
                application_id=str(application_a.id),
                status="pending",
            ),
            ApplicationMessage(
                application_id=str(application_a.id),
                sender_id=str(candidate_a.id),
                body="delete with job",
            ),
        ]
    )
    await db_session.commit()
    response = await client.delete(f"/jobs/{job_a.id}", headers=auth_header(employer_a))
    assert response.status_code == 200
    checks = (
        (JobDescription, JobDescription.id == str(job_a.id)),
        (JobApplication, JobApplication.id == str(application_a.id)),
        (MatchResult, MatchResult.job_id == str(job_a.id)),
        (InterviewInvitation, InterviewInvitation.job_id == str(job_a.id)),
        (ApplicationMessage, ApplicationMessage.application_id == str(application_a.id)),
    )
    for model, predicate in checks:
        count = (
            await db_session.execute(select(func.count()).select_from(model).where(predicate))
        ).scalar_one()
        assert count == 0, model.__name__


async def test_account_delete_removes_user_private_graph(
    client, auth_header, db_session, candidate_a, resume_a, application_a
):
    await sync_resume_claims(
        db_session,
        resume_a,
        actor_id=str(candidate_a.id),
        reason="account_delete_test",
    )
    db_session.add(
        UsageEvent(
            user_id=str(candidate_a.id),
            feature="pr4-delete",
            month_key="2026-07",
        )
    )
    await db_session.commit()
    response = await client.delete("/auth/account", headers=auth_header(candidate_a))
    assert response.status_code == 200
    checks = (
        (User, User.id == str(candidate_a.id)),
        (Resume, Resume.id == str(resume_a.id)),
        (ResumeClaim, ResumeClaim.resume_id == str(resume_a.id)),
        (ClaimEvent, ClaimEvent.actor_id == str(candidate_a.id)),
        (JobApplication, JobApplication.id == str(application_a.id)),
        (UsageEvent, UsageEvent.user_id == str(candidate_a.id)),
    )
    for model, predicate in checks:
        count = (
            await db_session.execute(select(func.count()).select_from(model).where(predicate))
        ).scalar_one()
        assert count == 0, model.__name__
