"""PR7 migration helper unit tests (no database)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.migration_sql import (
    MIGRATION_DIR,
    checksum_mismatches,
    expected_migration_checksum,
    split_sql,
)
from app.schema_version import ALEMBIC_HEAD, EXPECTED_MIGRATIONS, LEDGER_TO_ALEMBIC


def test_split_sql_skips_empty():
    statements = split_sql("SELECT 1;\n\n; SELECT 2; ")
    assert statements == ["SELECT 1", "SELECT 2"]


def test_split_sql_preserves_semicolons_in_postgres_constructs():
    sql = """
    -- a comment containing ; must not split
    INSERT INTO demo(value) VALUES ('alpha;beta');
    INSERT INTO demo(value) VALUES ('it''s;safe');
    CREATE FUNCTION demo_fn() RETURNS void AS $body$
    BEGIN
        PERFORM 'inside;body';
    END;
    $body$ LANGUAGE plpgsql;
    /* block ; comment */
    SELECT "semi;colon";
    """
    statements = split_sql(sql)
    assert len(statements) == 4
    assert "'alpha;beta'" in statements[0]
    assert "'it''s;safe'" in statements[1]
    assert "PERFORM 'inside;body';" in statements[2]
    assert '"semi;colon"' in statements[3]


def test_split_sql_rejects_unterminated_quoted_construct():
    with pytest.raises(ValueError, match="unterminated SQL construct"):
        split_sql("INSERT INTO demo(value) VALUES ('broken);")


def test_expected_migrations_include_pr10_and_match_alembic_head():
    assert "20260726_pr7_constraints" in EXPECTED_MIGRATIONS
    assert "20260726_pr8_claim_passport" in EXPECTED_MIGRATIONS
    assert "20260726_pr9_potential_simulation" in EXPECTED_MIGRATIONS
    assert "20260728_pr10_ai_gateway_data_sources" in EXPECTED_MIGRATIONS
    assert "20260728_pr11_career_passport_vault" in EXPECTED_MIGRATIONS
    assert "20260729_pr11_idempotency_storage" in EXPECTED_MIGRATIONS
    assert "20260729_pr12_interview_sessions" in EXPECTED_MIGRATIONS
    assert "20260729_pr13_target_job_optimization" in EXPECTED_MIGRATIONS
    assert "20260729_pr14_advisor_profiles" in EXPECTED_MIGRATIONS
    assert "20260731_pr15_screening" in EXPECTED_MIGRATIONS
    assert "20260813_c5_inference_hypotheses" in EXPECTED_MIGRATIONS
    assert "20260814_pilot_readiness" in EXPECTED_MIGRATIONS
    assert "20260815_account_recovery" in EXPECTED_MIGRATIONS
    assert "20260815_legal_acceptance" in EXPECTED_MIGRATIONS
    assert LEDGER_TO_ALEMBIC["20260728_pr10_ai_gateway_data_sources"] == "pr10_ai_gateway"
    assert LEDGER_TO_ALEMBIC["20260729_pr11_idempotency_storage"] == "pr11_idempotency"
    assert LEDGER_TO_ALEMBIC["20260729_pr13_target_job_optimization"] == "pr13_target_job"
    assert LEDGER_TO_ALEMBIC["20260729_pr14_advisor_profiles"] == "pr14_advisor_profiles"
    assert LEDGER_TO_ALEMBIC["20260731_pr15_screening"] == "pr15_screening"
    assert LEDGER_TO_ALEMBIC["20260813_c5_inference_hypotheses"] == "c5_inference_hypotheses"
    assert LEDGER_TO_ALEMBIC["20260814_pilot_readiness"] == "pilot_readiness"
    assert LEDGER_TO_ALEMBIC["20260815_account_recovery"] == "account_recovery"
    assert LEDGER_TO_ALEMBIC["20260815_legal_acceptance"] == "legal_acceptance"
    assert ALEMBIC_HEAD == "legal_acceptance"
    assert len(ALEMBIC_HEAD) <= 32
    assert set(LEDGER_TO_ALEMBIC) == set(EXPECTED_MIGRATIONS)
    assert all(len(v) <= 32 for v in LEDGER_TO_ALEMBIC.values())
    assert "20260729_pr12_interview_sessions" in EXPECTED_MIGRATIONS


def test_checksum_mismatch_rejects_changed_published_sql():
    version = EXPECTED_MIGRATIONS[-1]
    checksum = expected_migration_checksum(version)

    assert checksum_mismatches([(version, checksum)]) == []
    assert checksum_mismatches([(version, "0" * 64)]) == [version]
    assert checksum_mismatches([("missing_revision", checksum)]) == ["missing_revision"]


def test_pr7_down_handles_constraints_created_by_orm_baseline():
    down = (MIGRATION_DIR / "20260726_pr7_constraints_down.sql").read_text(encoding="utf-8")
    assert (
        "ALTER TABLE job_applications\n"
        "    DROP CONSTRAINT IF EXISTS uq_job_applications_candidate_job"
    ) in down
    assert (
        "ALTER TABLE match_results\n    DROP CONSTRAINT IF EXISTS uq_match_results_resume_job"
    ) in down


def test_pr8_migration_has_all_passport_tables_and_reversible_order():
    upgrade = (MIGRATION_DIR / "20260726_pr8_claim_passport_up.sql").read_text(encoding="utf-8")
    downgrade = (MIGRATION_DIR / "20260726_pr8_claim_passport_down.sql").read_text(encoding="utf-8")
    for table in (
        "resume_claims",
        "claim_evidence",
        "claim_revisions",
        "claim_application_links",
        "claim_events",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in upgrade
        assert f"DROP TABLE IF EXISTS {table}" in downgrade
    assert downgrade.index("claim_events") < downgrade.index("resume_claims")


def test_pr9_migration_keeps_candidate_simulation_events_reversible():
    upgrade = (MIGRATION_DIR / "20260726_pr9_potential_simulation_up.sql").read_text(
        encoding="utf-8"
    )
    downgrade = (MIGRATION_DIR / "20260726_pr9_potential_simulation_down.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE IF NOT EXISTS potential_simulation_events" in upgrade
    assert "result_snapshot JSONB NOT NULL" in upgrade
    assert "DROP TABLE IF EXISTS potential_simulation_events" in downgrade


def test_pr10_migration_has_gateway_tables_and_reversible_order():
    upgrade = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "migrations"
        / "20260728_pr10_ai_gateway_data_sources_up.sql"
    ).read_text(encoding="utf-8")
    downgrade = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "migrations"
        / "20260728_pr10_ai_gateway_data_sources_down.sql"
    ).read_text(encoding="utf-8")
    for table in ("data_sources", "data_source_versions", "ai_invocations"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in upgrade
        assert f"DROP TABLE IF EXISTS {table}" in downgrade
    assert downgrade.index("ai_invocations") < downgrade.index("data_sources")


def test_pr11_migration_extends_claims_without_recreating_ids():
    upgrade = (MIGRATION_DIR / "20260728_pr11_career_passport_vault_up.sql").read_text(
        encoding="utf-8"
    )
    downgrade = (MIGRATION_DIR / "20260728_pr11_career_passport_vault_down.sql").read_text(
        encoding="utf-8"
    )
    for table in (
        "career_experiences",
        "evidence_artifacts",
        "resume_versions",
        "resume_version_claim_links",
        "migration_orphan_reports",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in upgrade
    assert "ALTER TABLE resume_claims ADD COLUMN" in upgrade
    assert "DROP TABLE IF EXISTS resume_claims" not in upgrade
    assert "UPDATE resume_claims AS claim" in upgrade
    assert "downgrade refused" in downgrade


def test_pr11_idempotency_migration_is_reversible():
    upgrade = (MIGRATION_DIR / "20260729_pr11_idempotency_storage_up.sql").read_text(
        encoding="utf-8"
    )
    downgrade = (MIGRATION_DIR / "20260729_pr11_idempotency_storage_down.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE IF NOT EXISTS api_idempotency_keys" in upgrade
    assert "uq_api_idempotency_user_scope_key" in upgrade
    assert "DROP TABLE IF EXISTS api_idempotency_keys" in downgrade


def test_pr12_migration_has_structured_interview_tables():
    upgrade = (MIGRATION_DIR / "20260729_pr12_interview_sessions_up.sql").read_text(
        encoding="utf-8"
    )
    downgrade = (MIGRATION_DIR / "20260729_pr12_interview_sessions_down.sql").read_text(
        encoding="utf-8"
    )
    for table in (
        "interview_sessions",
        "interview_questions",
        "interview_answers",
        "interview_observations",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in upgrade
        assert f"DROP TABLE IF EXISTS {table}" in downgrade
    assert "structured_session_id" in upgrade
    assert "downgrade refused" in downgrade
