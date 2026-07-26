"""PR5.1 pricing and interview usage sessions.

Revision ID: pr5_1_pricing_interview
Revises: pr5_1_provider_costs
Create Date: 2026-07-25
"""
from __future__ import annotations

from typing import Sequence, Union

from app.migration_sql import apply_named_sql_migration, revert_named_sql_migration

revision: str = "pr5_1_pricing_interview"
down_revision: Union[str, Sequence[str], None] = "pr5_1_provider_costs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VERSION = "20260725_pr5_1_pricing_and_interview"


def upgrade() -> None:
    apply_named_sql_migration(VERSION)


def downgrade() -> None:
    revert_named_sql_migration(VERSION)
