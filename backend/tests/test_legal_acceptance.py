from sqlalchemy import func, select

from app.auth_routes import PRIVACY_NOTICE_VERSION, TERMS_VERSION
from app.models_db import LegalAcceptance, User


async def test_registration_requires_and_records_versioned_notices(
    client, db_session, billing_catalog
):
    payload = {
        "email": "legal-candidate@test.local",
        "password": "StrongLegal9Z!",
    }
    missing = await client.post("/auth/register", json=payload)
    assert missing.status_code == 422

    created = await client.post(
        "/auth/register",
        json={
            **payload,
            "terms_accepted": True,
            "privacy_notice_acknowledged": True,
        },
    )
    assert created.status_code == 200, created.text

    user = (
        await db_session.execute(select(User).where(User.email == payload["email"]))
    ).scalar_one()
    acceptance = (
        await db_session.execute(
            select(LegalAcceptance).where(LegalAcceptance.user_id == str(user.id))
        )
    ).scalar_one()
    assert acceptance.terms_version == TERMS_VERSION
    assert acceptance.privacy_notice_version == PRIVACY_NOTICE_VERSION
    assert acceptance.notice_snapshot["terms_version"] == TERMS_VERSION


async def test_legal_notice_is_public_and_account_deletion_cascades_acceptance(
    client, db_session, billing_catalog
):
    notice = await client.get("/auth/legal-notice")
    assert notice.status_code == 200
    assert notice.json()["terms_version"] == TERMS_VERSION
    assert notice.json()["privacy_notice_version"] == PRIVACY_NOTICE_VERSION

    created = await client.post(
        "/auth/register",
        json={
            "email": "legal-delete@test.local",
            "password": "StrongLegal8Y!",
            "terms_accepted": True,
            "privacy_notice_acknowledged": True,
        },
    )
    user_id = created.json()["user_id"]
    login = await client.post(
        "/auth/login",
        json={"email": "legal-delete@test.local", "password": "StrongLegal8Y!"},
    )
    deleted = await client.delete(
        "/auth/account",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert deleted.status_code == 200
    remaining = (
        await db_session.execute(
            select(func.count())
            .select_from(LegalAcceptance)
            .where(LegalAcceptance.user_id == user_id)
        )
    ).scalar_one()
    assert remaining == 0
