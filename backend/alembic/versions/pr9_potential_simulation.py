"""PR9 deterministic potential simulation events."""

from __future__ import annotations
from typing import Sequence, Union
from app.migration_sql import apply_named_sql_migration, revert_named_sql_migration

revision: str = "pr9_potential_simulation"
down_revision: Union[str, Sequence[str], None] = "pr8_claim_passport"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
VERSION = "20260726_pr9_potential_simulation"


def upgrade() -> None:
    apply_named_sql_migration(VERSION)


def downgrade() -> None:
    revert_named_sql_migration(VERSION)
