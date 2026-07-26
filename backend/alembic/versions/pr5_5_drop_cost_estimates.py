"""PR5.5 remove legacy cost estimate columns.

Revision ID: pr5_5_drop_cost_estimates
Revises: pr5_1_interview_results
Create Date: 2026-07-25
"""
from __future__ import annotations

from typing import Sequence, Union

from app.migration_sql import apply_named_sql_migration, revert_named_sql_migration

revision: str = "pr5_5_drop_cost_estimates"
down_revision: Union[str, Sequence[str], None] = "pr5_1_interview_results"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VERSION = "20260725_pr5_5_remove_legacy_cost_estimates"


def upgrade() -> None:
    apply_named_sql_migration(VERSION)


def downgrade() -> None:
    revert_named_sql_migration(VERSION)
