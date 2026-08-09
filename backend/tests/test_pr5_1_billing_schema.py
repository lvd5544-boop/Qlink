from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.database import engine


pytestmark = pytest.mark.asyncio


async def test_billing_organization_is_distinct_from_market_company(db_session):
    from app.models_db import Company, Organization

    company = Company(name="示例企业")
    organization = Organization(name="示例企业")
    db_session.add_all([company, organization])
    await db_session.commit()

    assert company.__tablename__ == "companies"
    assert organization.__tablename__ == "organizations"
    assert company.id != organization.id


async def test_one_user_occupies_only_one_membership_per_organization(db_session, employer_a):
    from app.models_db import Organization, OrganizationMembership

    organization = Organization(name="企业租户 A")
    db_session.add(organization)
    await db_session.flush()
    db_session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=employer_a.id,
            role="owner",
            status="active",
        )
    )
    await db_session.commit()

    db_session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=employer_a.id,
            role="recruiter",
            status="active",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_plan_money_is_integer_cny_and_entitlements_are_versioned(
    db_session,
):
    from app.models_db import Plan, PlanEntitlement

    plan = Plan(
        code="candidate-pro-v1",
        audience="candidate",
        name="Candidate Pro",
        currency="CNY",
        price_minor_units=2000,
        billing_period="month",
        version=1,
        active=True,
    )
    db_session.add(plan)
    await db_session.flush()
    db_session.add(
        PlanEntitlement(
            plan_code=plan.code,
            feature="resume_coach",
            limit_units=50,
            period="month",
            meter_type="paid_credit",
        )
    )
    await db_session.commit()

    stored = (await db_session.execute(select(Plan).where(Plan.code == plan.code))).scalar_one()
    assert stored.currency == "CNY"
    assert stored.price_minor_units == 2000
    assert isinstance(stored.price_minor_units, int)
    assert stored.version == 1


async def test_candidate_and_organization_subscriptions_have_explicit_periods(
    db_session, candidate_a
):
    from app.models_db import (
        Organization,
        OrganizationSubscription,
        Plan,
        UserSubscription,
    )

    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=30)
    candidate_plan = Plan(
        code="candidate-free-v1",
        audience="candidate",
        name="Candidate Free",
        currency="CNY",
        price_minor_units=0,
        billing_period="month",
        version=1,
        active=True,
    )
    organization_plan = Plan(
        code="organization-seat-v1",
        audience="organization",
        name="Organization",
        currency="CNY",
        price_minor_units=30000,
        billing_period="month",
        version=1,
        active=True,
    )
    organization = Organization(name="企业租户 B")
    db_session.add_all([candidate_plan, organization_plan, organization])
    await db_session.flush()
    db_session.add_all(
        [
            UserSubscription(
                user_id=candidate_a.id,
                plan_code=candidate_plan.code,
                status="active",
                period_start=now,
                period_end=period_end,
                cancel_at_period_end=False,
                source="pilot",
            ),
            OrganizationSubscription(
                organization_id=organization.id,
                plan_code=organization_plan.code,
                seat_quantity=1,
                status="active",
                period_start=now,
                period_end=period_end,
                cancel_at_period_end=False,
                source="pilot",
            ),
        ]
    )
    await db_session.commit()


async def test_billing_core_migration_declares_all_authoritative_tables():
    migration_dir = Path(__file__).resolve().parents[1] / "scripts" / "migrations"
    upgrade = (migration_dir / "20260725_pr5_1_billing_core_up.sql").read_text(encoding="utf-8")
    downgrade = (migration_dir / "20260725_pr5_1_billing_core_down.sql").read_text(encoding="utf-8")

    for table in (
        "organization_memberships",
        "plans",
        "plan_entitlements",
        "user_subscriptions",
        "organization_subscriptions",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in upgrade
        assert f"DROP TABLE IF EXISTS {table}" in downgrade
    assert "CREATE TABLE IF NOT EXISTS organizations" in upgrade
    assert "DROP TABLE IF EXISTS organizations" not in downgrade


async def test_pricing_catalog_matches_confirmed_cny_rules():
    migration_dir = Path(__file__).resolve().parents[1] / "scripts" / "migrations"
    upgrade = (migration_dir / "20260725_pr5_1_pricing_and_interview_up.sql").read_text(
        encoding="utf-8"
    )

    expected_fragments = (
        "('candidate-free-v1', 'candidate', 'Candidate Free', 'CNY', 0",
        "('candidate-pro-v1', 'candidate', 'Candidate Pro', 'CNY', 2000",
        "('organization-seat-v1', 'organization', '企业席位', 'CNY', 30000",
        "'candidate-free-v1', 'resume_coach', 50, 'month'",
        "'candidate-free-v1', 'evidence_regenerate', 50, 'month'",
        "'candidate-pro-v1', 'resume_coach', 50, 'month'",
        "'candidate-pro-v1', 'evidence_regenerate', 50, 'month'",
        "'interview_session', 50, 'day', 'fair_use'",
        "'interview_turn', 50, 'session', 'fair_use'",
        "'organization-seat-v1', 'credibility_audit', 300, 'month'",
        "'organization-audit-100-v1'",
        "10000",
        "100",
    )
    for fragment in expected_fragments:
        assert fragment in upgrade


async def test_postgres_pricing_catalog_migration_up_down_up():
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL migration contract")

    migration_dir = Path(__file__).resolve().parents[1] / "scripts" / "migrations"
    upgrade = (migration_dir / "20260725_pr5_1_pricing_and_interview_up.sql").read_text(
        encoding="utf-8"
    )
    downgrade = (migration_dir / "20260725_pr5_1_pricing_and_interview_down.sql").read_text(
        encoding="utf-8"
    )
    interview_result_upgrade = (
        migration_dir / "20260725_pr5_1_interview_results_up.sql"
    ).read_text(encoding="utf-8")
    interview_result_downgrade = (
        migration_dir / "20260725_pr5_1_interview_results_down.sql"
    ).read_text(encoding="utf-8")
    structured_interview_upgrade = (
        migration_dir / "20260729_pr12_interview_sessions_up.sql"
    ).read_text(encoding="utf-8")

    async with engine.begin() as connection:
        # Respect stack order: a newer table references interview sessions,
        # so rollback the newer migration before the older one.
        for sql in (
            interview_result_downgrade,
            upgrade,
            downgrade,
            upgrade,
            interview_result_upgrade,
            # Restore the current schema after exercising the historical
            # PR5.1 round trip so later PostgreSQL tests stay isolated.
            structured_interview_upgrade,
        ):
            for statement in (part.strip() for part in sql.split(";")):
                if statement:
                    await connection.exec_driver_sql(statement)

        rows = (
            await connection.exec_driver_sql(
                """
                SELECT code, price_minor_units
                FROM plans
                WHERE code IN (
                    'candidate-free-v1',
                    'candidate-pro-v1',
                    'organization-seat-v1'
                )
                ORDER BY code
                """
            )
        ).all()
        assert rows == [
            ("candidate-free-v1", 0),
            ("candidate-pro-v1", 2000),
            ("organization-seat-v1", 30000),
        ]
        pack = (
            await connection.exec_driver_sql(
                """
                SELECT price_minor_units, grant_units
                FROM credit_pack_products
                WHERE code = 'organization-audit-100-v1'
                """
            )
        ).one()
        assert pack == (10000, 100)


async def test_postgres_legacy_estimated_cost_cleanup_up_down_up():
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL migration contract")

    migration_dir = Path(__file__).resolve().parents[1] / "scripts" / "migrations"
    upgrade = (migration_dir / "20260725_pr5_5_remove_legacy_cost_estimates_up.sql").read_text(
        encoding="utf-8"
    )
    downgrade = (migration_dir / "20260725_pr5_5_remove_legacy_cost_estimates_down.sql").read_text(
        encoding="utf-8"
    )

    async with engine.begin() as connection:
        for sql in (upgrade, downgrade, upgrade):
            for statement in (part.strip() for part in sql.split(";")):
                if statement:
                    await connection.exec_driver_sql(statement)
        columns = await connection.run_sync(
            lambda sync_connection: {
                table: {column["name"] for column in inspect(sync_connection).get_columns(table)}
                for table in ("usage_events", "usage_reservations")
            }
        )
        assert "estimated_cost_usd" not in columns["usage_events"]
        assert "estimated_cost_usd" not in columns["usage_reservations"]


async def test_postgres_billing_core_migration_up_down_up():
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL migration contract")

    migration_dir = Path(__file__).resolve().parents[1] / "scripts" / "migrations"
    upgrade = (migration_dir / "20260725_pr5_1_billing_core_up.sql").read_text(encoding="utf-8")
    downgrade = (migration_dir / "20260725_pr5_1_billing_core_down.sql").read_text(encoding="utf-8")

    async with engine.begin() as connection:
        for sql in (upgrade, downgrade, upgrade):
            for statement in (part.strip() for part in sql.split(";")):
                if statement:
                    await connection.exec_driver_sql(statement)

        table_names = await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).get_table_names()
        )
        assert "organizations" in table_names
        assert "organization_subscriptions" in table_names


async def test_organization_members_share_one_audit_credit_pool(
    db_session,
    employer_a,
    employer_b,
    monkeypatch,
):
    from app.billing_accounts import reserve_feature_entitlement
    from app.models_db import (
        Organization,
        OrganizationMembership,
        OrganizationSubscription,
        Plan,
        PlanEntitlement,
    )

    now = datetime.now(timezone.utc)
    organization = Organization(name="共享额度企业")
    plan = Plan(
        code="organization-shared-test-v1",
        audience="organization",
        name="Organization Shared Test",
        currency="CNY",
        price_minor_units=30000,
        billing_period="month",
        version=1,
        active=True,
    )
    db_session.add_all([organization, plan])
    await db_session.flush()
    db_session.add_all(
        [
            OrganizationMembership(
                organization_id=organization.id,
                user_id=employer_a.id,
                role="owner",
                status="active",
            ),
            OrganizationMembership(
                organization_id=organization.id,
                user_id=employer_b.id,
                role="recruiter",
                status="active",
            ),
            PlanEntitlement(
                plan_code=plan.code,
                feature="credibility_audit",
                limit_units=1,
                period="month",
                meter_type="paid_credit",
            ),
            OrganizationSubscription(
                organization_id=organization.id,
                plan_code=plan.code,
                seat_quantity=2,
                status="active",
                period_start=now - timedelta(days=1),
                period_end=now + timedelta(days=29),
                cancel_at_period_end=False,
                source="pilot",
            ),
        ]
    )
    await db_session.commit()
    monkeypatch.setenv("METERING_ENABLED", "true")

    first = await reserve_feature_entitlement(
        db_session,
        actor=employer_a,
        feature="credibility_audit",
        idempotency_key="org-shared-1",
        request_payload={"application_id": "application-a"},
    )
    assert first["created"] is True

    with pytest.raises(HTTPException) as exc_info:
        await reserve_feature_entitlement(
            db_session,
            actor=employer_b,
            feature="credibility_audit",
            idempotency_key="org-shared-2",
            request_payload={"application_id": "application-b"},
        )
    # Exhausting a plan entitlement is rate/quota exhaustion, not payment
    # authorization failure. Credit-pack purchase is a separate product flow.
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["error"] == "quota_exceeded"


async def test_postgres_metering_and_cost_migrations_preserve_cost_audit():
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL migration contract")

    migration_dir = Path(__file__).resolve().parents[1] / "scripts" / "migrations"

    def read(name: str) -> str:
        return (migration_dir / name).read_text(encoding="utf-8")

    async def execute_script(connection, sql: str) -> None:
        for statement in (part.strip() for part in sql.split(";")):
            if statement:
                await connection.exec_driver_sql(statement)

    async with engine.begin() as connection:
        await execute_script(
            connection,
            read("20260725_pr5_usage_reservations_up.sql"),
        )
        await execute_script(
            connection,
            read("20260725_pr5_1_billing_core_up.sql"),
        )
        await execute_script(
            connection,
            read("20260725_pr5_1_provider_costs_up.sql"),
        )
        await execute_script(
            connection,
            read("20260725_pr5_1_metering_accounts_up.sql"),
        )
        await execute_script(
            connection,
            read("20260725_pr5_1_metering_accounts_down.sql"),
        )
        await execute_script(
            connection,
            read("20260725_pr5_1_metering_accounts_up.sql"),
        )
        await execute_script(
            connection,
            read("20260725_pr5_1_provider_costs_down.sql"),
        )

        columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"]
                for column in inspect(sync_connection).get_columns("usage_reservations")
            }
        )
        tables = await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).get_table_names()
        )
        assert {
            "billing_account_type",
            "billing_account_id",
            "period_key",
            "request_fingerprint",
            "attempt",
            "model_called",
            "finalized_at",
        } <= columns
        assert "provider_cost_events" in tables
