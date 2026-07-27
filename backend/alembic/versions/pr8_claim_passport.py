"""PR8 Claim Passport.

Revision ID: pr8_claim_passport
Revises: pr7_constraints
"""
from __future__ import annotations

from typing import Sequence, Union

from app.migration_sql import apply_named_sql_migration, revert_named_sql_migration

revision: str = "pr8_claim_passport"
down_revision: Union[str, Sequence[str], None] = "pr7_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VERSION = "20260726_pr8_claim_passport"


def upgrade() -> None:
    apply_named_sql_migration(VERSION)


def downgrade() -> None:
    revert_named_sql_migration(VERSION)
