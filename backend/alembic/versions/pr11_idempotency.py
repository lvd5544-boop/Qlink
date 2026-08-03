"""PR11 follow-up: API idempotency ledger for Career Passport / Evidence Vault writes."""

from __future__ import annotations
from typing import Sequence, Union
from app.migration_sql import apply_named_sql_migration, revert_named_sql_migration

revision: str = "pr11_idempotency"
down_revision: Union[str, Sequence[str], None] = "pr11_passport_vault"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
VERSION = "20260729_pr11_idempotency_storage"


def upgrade() -> None:
    apply_named_sql_migration(VERSION)


def downgrade() -> None:
    revert_named_sql_migration(VERSION)
