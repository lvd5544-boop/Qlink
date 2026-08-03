"""PR10 AI gateway, data sources registry, and invocation audit tables."""

from __future__ import annotations
from typing import Sequence, Union
from app.migration_sql import apply_named_sql_migration, revert_named_sql_migration

revision: str = "pr10_ai_gateway"
down_revision: Union[str, Sequence[str], None] = "pr9_potential_simulation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
VERSION = "20260728_pr10_ai_gateway_data_sources"


def upgrade() -> None:
    apply_named_sql_migration(VERSION)


def downgrade() -> None:
    revert_named_sql_migration(VERSION)
