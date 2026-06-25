"""
Idempotent PostgreSQL schema alignment for SQLAlchemy models.

Structured frequency/distribution fields are stored as PostgreSQL ``json`` (not Excel).
Excel/CSV is only suitable for one-off imports; the API and ORM use JSON objects.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = logging.getLogger(__name__)


async def _column_exists(conn: AsyncConnection, table: str, column: str) -> bool:
    result = await conn.execute(
        text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table
              AND column_name = :column
            """
        ),
        {"table": table, "column": column},
    )
    return result.scalar() is not None


async def _migrate_hired_profile_benchmarks(conn: AsyncConnection) -> None:
    table = "hired_profile_benchmarks"

    for old_name, new_name in (
        ("school_tier_freq", "school_tier_dist"),
        ("education_freq", "degree_freq"),
    ):
        if await _column_exists(conn, table, old_name) and not await _column_exists(
            conn, table, new_name
        ):
            await conn.execute(
                text(f'ALTER TABLE "{table}" RENAME COLUMN "{old_name}" TO "{new_name}"')
            )
            logger.info("Renamed %s.%s -> %s", table, old_name, new_name)

    for column, ddl in (
        ("confidence_score", "DOUBLE PRECISION"),
        ("source_breakdown", "JSON DEFAULT '{}'::json"),
        ("statistical_summary", "JSON DEFAULT '{}'::json"),
        ("methodology", "TEXT"),
    ):
        if not await _column_exists(conn, table, column):
            await conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))
            logger.info("Added %s.%s", table, column)


async def _migrate_forum_insight_extracted(conn: AsyncConnection) -> None:
    table = "forum_insight_extracted"
    for column, ddl in (
        ("post_type", "VARCHAR(20) DEFAULT 'discussion'"),
        ("recruitment_type", "VARCHAR(20) DEFAULT 'unknown'"),
    ):
        if not await _column_exists(conn, table, column):
            await conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))
            logger.info("Added %s.%s", table, column)


async def _migrate_match_results(conn: AsyncConnection) -> None:
    table = "match_results"
    if not await _column_exists(conn, table, "score_breakdown"):
        await conn.execute(
            text(f'ALTER TABLE "{table}" ADD COLUMN "score_breakdown" JSON')
        )
        logger.info("Added %s.score_breakdown", table)


async def _migrate_resumes(conn: AsyncConnection) -> None:
    table = "resumes"
    if not await _column_exists(conn, table, "health_check"):
        await conn.execute(
            text(f'ALTER TABLE "{table}" ADD COLUMN "health_check" JSON')
        )
        logger.info("Added %s.health_check", table)


async def ensure_schema(engine: AsyncEngine) -> None:
    """Bring legacy databases in line with models_db (safe to run every startup)."""
    async with engine.begin() as conn:
        await _migrate_hired_profile_benchmarks(conn)
        await _migrate_forum_insight_extracted(conn)
        await _migrate_match_results(conn)
        await _migrate_resumes(conn)
