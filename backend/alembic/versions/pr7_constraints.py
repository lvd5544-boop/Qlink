"""PR7 unique constraints and indexes.

Revision ID: pr7_constraints
Revises: pr5_5_drop_cost_estimates
Create Date: 2026-07-26
"""
from __future__ import annotations

from typing import Sequence, Union

from app.migration_sql import apply_named_sql_migration, revert_named_sql_migration

revision: str = "pr7_constraints"
down_revision: Union[str, Sequence[str], None] = (
    "pr5_5_drop_cost_estimates"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VERSION = "20260726_pr7_constraints"


def upgrade() -> None:
    apply_named_sql_migration(VERSION)


def downgrade() -> None:
    revert_named_sql_migration(VERSION)
