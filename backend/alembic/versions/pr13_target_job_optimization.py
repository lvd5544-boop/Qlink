"""PR13 target-job diagnostics, faithful rewrite and readiness."""

from __future__ import annotations
from typing import Sequence, Union
from app.migration_sql import apply_named_sql_migration, revert_named_sql_migration

revision: str = "pr13_target_job"
down_revision: Union[str, Sequence[str], None] = "pr12_interview_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
VERSION = "20260729_pr13_target_job_optimization"


def upgrade() -> None:
    apply_named_sql_migration(VERSION)


def downgrade() -> None:
    revert_named_sql_migration(VERSION)
