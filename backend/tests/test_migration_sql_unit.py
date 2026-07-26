"""PR7 migration helper unit tests (no database)."""

from __future__ import annotations

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


def test_expected_migrations_include_pr7_and_match_alembic_head():
    assert "20260726_pr7_constraints" in EXPECTED_MIGRATIONS
    assert ALEMBIC_HEAD == "pr7_constraints"
    assert len(ALEMBIC_HEAD) <= 32
    assert set(LEDGER_TO_ALEMBIC) == set(EXPECTED_MIGRATIONS)
    assert all(len(v) <= 32 for v in LEDGER_TO_ALEMBIC.values())


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
