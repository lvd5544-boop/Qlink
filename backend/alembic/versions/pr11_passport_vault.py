"""PR11 Career Passport and Evidence Vault."""

from __future__ import annotations
from typing import Sequence, Union
from app.migration_sql import apply_named_sql_migration, revert_named_sql_migration

revision: str = "pr11_passport_vault"
down_revision: Union[str, Sequence[str], None] = "pr10_ai_gateway"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
VERSION = "20260728_pr11_career_passport_vault"


def upgrade() -> None:
    apply_named_sql_migration(VERSION)


def downgrade() -> None:
    revert_named_sql_migration(VERSION)
