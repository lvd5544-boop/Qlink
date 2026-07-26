"""PR5.1 interview results.

Revision ID: pr5_1_interview_results
Revises: pr5_1_pricing_interview
Create Date: 2026-07-25
"""
from __future__ import annotations

from typing import Sequence, Union

from app.migration_sql import apply_named_sql_migration, revert_named_sql_migration

revision: str = "pr5_1_interview_results"
down_revision: Union[str, Sequence[str], None] = (
    "pr5_1_pricing_interview"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VERSION = "20260725_pr5_1_interview_results"


def upgrade() -> None:
    apply_named_sql_migration(VERSION)


def downgrade() -> None:
    revert_named_sql_migration(VERSION)
