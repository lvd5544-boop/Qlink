"""Read-only schema version checks used by startup and readiness."""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


EXPECTED_MIGRATIONS = (
    "20260725_pr5_1_billing_core",
    "20260725_pr5_1_metering_accounts",
    "20260725_pr5_1_provider_costs",
    "20260725_pr5_1_pricing_and_interview",
    "20260725_pr5_1_interview_results",
    "20260725_pr5_5_remove_legacy_cost_estimates",
    "20260726_pr7_constraints",
    "20260726_pr8_claim_passport",
    "20260726_pr9_potential_simulation",
    "20260728_pr10_ai_gateway_data_sources",
    "20260728_pr11_career_passport_vault",
    "20260729_pr11_idempotency_storage",
    "20260729_pr12_interview_sessions",
    "20260729_pr13_target_job_optimization",
    "20260729_pr14_advisor_profiles",
    "20260731_pr15_screening",
)

# Alembic version_num is VARCHAR(32); keep short revision ids mapped 1:1.
LEDGER_TO_ALEMBIC = {
    "20260725_pr5_1_billing_core": "pr5_1_billing_core",
    "20260725_pr5_1_metering_accounts": "pr5_1_metering_accounts",
    "20260725_pr5_1_provider_costs": "pr5_1_provider_costs",
    "20260725_pr5_1_pricing_and_interview": "pr5_1_pricing_interview",
    "20260725_pr5_1_interview_results": "pr5_1_interview_results",
    "20260725_pr5_5_remove_legacy_cost_estimates": "pr5_5_drop_cost_estimates",
    "20260726_pr7_constraints": "pr7_constraints",
    "20260726_pr8_claim_passport": "pr8_claim_passport",
    "20260726_pr9_potential_simulation": "pr9_potential_simulation",
    "20260728_pr10_ai_gateway_data_sources": "pr10_ai_gateway",
    "20260728_pr11_career_passport_vault": "pr11_passport_vault",
    "20260729_pr11_idempotency_storage": "pr11_idempotency",
    "20260729_pr12_interview_sessions": "pr12_interview_sessions",
    "20260729_pr13_target_job_optimization": "pr13_target_job",
    "20260729_pr14_advisor_profiles": "pr14_advisor_profiles",
    "20260731_pr15_screening": "pr15_screening",
}
ALEMBIC_HEAD = LEDGER_TO_ALEMBIC[EXPECTED_MIGRATIONS[-1]]


@dataclass(frozen=True)
class SchemaStatus:
    ready: bool
    applied: tuple[str, ...]
    missing: tuple[str, ...]


def schema_version_required() -> bool:
    configured = os.getenv("REQUIRE_SCHEMA_VERSION", "").strip().lower()
    if configured:
        return configured in {"1", "true", "yes"}
    return os.getenv("ENV", "development").strip().lower() == "production"


async def inspect_schema(engine: AsyncEngine) -> SchemaStatus:
    async with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            exists = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'schema_migrations'"
                )
            )
        else:
            exists = await connection.scalar(
                text("SELECT to_regclass('public.schema_migrations') IS NOT NULL")
            )
        if not exists:
            return SchemaStatus(False, (), EXPECTED_MIGRATIONS)

        rows = await connection.execute(
            text("SELECT version FROM schema_migrations ORDER BY version")
        )
        applied = tuple(str(row[0]) for row in rows)
    missing = tuple(item for item in EXPECTED_MIGRATIONS if item not in applied)
    return SchemaStatus(not missing, applied, missing)


async def require_current_schema(engine: AsyncEngine) -> None:
    if not schema_version_required():
        return
    status = await inspect_schema(engine)
    if not status.ready:
        missing = ", ".join(status.missing)
        raise RuntimeError(f"数据库迁移版本不完整；请先运行 migration 服务。 缺少: {missing}")
