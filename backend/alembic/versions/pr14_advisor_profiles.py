"""PR14 four-layer profiles, governed sources and grounded advisor."""

from __future__ import annotations
from typing import Sequence, Union
from app.migration_sql import apply_named_sql_migration, revert_named_sql_migration

revision: str = "pr14_advisor_profiles"
down_revision: Union[str, Sequence[str], None] = "pr13_target_job"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
VERSION = "20260729_pr14_advisor_profiles"


def upgrade() -> None:
    apply_named_sql_migration(VERSION)


def downgrade() -> None:
    revert_named_sql_migration(VERSION)
