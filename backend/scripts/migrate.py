#!/usr/bin/env python3
"""One-shot, auditable database migration entrypoint.

Only this command may mutate production schema. Application workers perform
read-only version validation and never call ``create_all`` or dynamic DDL.

PR7+: schema deltas are applied via Alembic. Existing SQL files remain the
authoritative body of each revision; Alembic owns ordering and the
``alembic_version`` table. The legacy ``schema_migrations`` ledger is kept in
sync for readiness checks.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.database import Base, engine
import app.models_db  # noqa: F401 - registers all ORM tables
from app.migration_sql import checksum_mismatches
from app.schema_version import EXPECTED_MIGRATIONS, LEDGER_TO_ALEMBIC


BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


async def _ensure_ledger(connection) -> None:
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(128) PRIMARY KEY,
                checksum VARCHAR(64) NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


async def _applied_ledger_versions(connection) -> list[str]:
    rows = await connection.execute(text("SELECT version FROM schema_migrations ORDER BY version"))
    return [str(row[0]) for row in rows]


async def _verify_ledger_checksums(connection) -> None:
    rows = await connection.execute(
        text("SELECT version, checksum FROM schema_migrations ORDER BY version")
    )
    mismatches = checksum_mismatches((str(row[0]), str(row[1])) for row in rows)
    if mismatches:
        raise RuntimeError(
            "已应用迁移 checksum 不一致；禁止修改已发布 SQL: " + ", ".join(mismatches)
        )


async def _alembic_version(connection) -> str | None:
    exists = await connection.scalar(
        text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
    )
    if not exists:
        return None
    return await connection.scalar(text("SELECT version_num FROM alembic_version"))


async def _bootstrap_and_stamp_target() -> str | None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await _ensure_ledger(connection)

    async with engine.connect() as connection:
        await _verify_ledger_checksums(connection)
        current = await _alembic_version(connection)
        if current:
            stamp_to = None
        else:
            applied = set(await _applied_ledger_versions(connection))
            stamp_to = None
            for version in EXPECTED_MIGRATIONS:
                if version in applied:
                    stamp_to = LEDGER_TO_ALEMBIC[version]
                else:
                    break

    # Release pool bindings before Alembic starts its own event loop.
    await engine.dispose()
    return stamp_to


async def _verify_ready() -> None:
    async with engine.connect() as connection:
        await _verify_ledger_checksums(connection)
        applied = await _applied_ledger_versions(connection)
        missing = [v for v in EXPECTED_MIGRATIONS if v not in applied]
        alembic_head = await _alembic_version(connection)
    await engine.dispose()
    if missing:
        raise RuntimeError("迁移完成后 schema_migrations 仍缺少: " + ", ".join(missing))
    print(f"ready alembic={alembic_head} ledger={len(applied)}")


def migrate() -> None:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("生产迁移仅支持 PostgreSQL")

    # Alembic env.py calls asyncio.run(); keep it outside any running loop and
    # dispose the shared async engine between loop lifetimes.
    stamp_to = asyncio.run(_bootstrap_and_stamp_target())
    if stamp_to:
        print(f"stamp alembic_version -> {stamp_to} (from schema_migrations)")
        command.stamp(_alembic_config(), stamp_to)

    print("alembic upgrade head")
    command.upgrade(_alembic_config(), "head")
    asyncio.run(_verify_ready())


if __name__ == "__main__":
    migrate()
