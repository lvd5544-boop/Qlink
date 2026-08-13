"""C5 bounded, candidate-resolvable inference hypotheses."""

from __future__ import annotations

from typing import Sequence, Union

from app.migration_sql import apply_named_sql_migration, revert_named_sql_migration

revision: str = "c5_inference_hypotheses"
down_revision: Union[str, Sequence[str], None] = "pr15_screening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
VERSION = "20260813_c5_inference_hypotheses"


def upgrade() -> None:
    apply_named_sql_migration(VERSION)


def downgrade() -> None:
    revert_named_sql_migration(VERSION)
