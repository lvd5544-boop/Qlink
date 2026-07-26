"""PR5.1 metering accounts.

Revision ID: pr5_1_metering_accounts
Revises: pr5_1_billing_core
Create Date: 2026-07-25
"""
from __future__ import annotations

from typing import Sequence, Union

from app.migration_sql import apply_named_sql_migration, revert_named_sql_migration

revision: str = "pr5_1_metering_accounts"
down_revision: Union[str, Sequence[str], None] = "pr5_1_billing_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VERSION = "20260725_pr5_1_metering_accounts"


def upgrade() -> None:
    apply_named_sql_migration(VERSION)


def downgrade() -> None:
    revert_named_sql_migration(VERSION)
