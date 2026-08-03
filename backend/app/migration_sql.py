"""Helpers that let Alembic revisions execute the repo's declarative SQL files."""

from __future__ import annotations

import hashlib
from pathlib import Path
from collections.abc import Iterable

from alembic import op
from sqlalchemy import text

MIGRATION_DIR = Path(__file__).resolve().parent.parent / "scripts" / "migrations"


def split_sql(sql: str) -> list[str]:
    """Split PostgreSQL SQL without treating quoted semicolons as delimiters.

    Migration files contain legal semicolons inside strings, identifiers,
    comments and dollar-quoted function bodies.  A plain ``str.split(";")``
    corrupts those statements and can leave a migration half-applied.
    """
    statements: list[str] = []
    current: list[str] = []
    index = 0
    state = "normal"
    dollar_tag = ""

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if state == "normal":
            if char == "'":
                state = "single_quote"
                current.append(char)
            elif char == '"':
                state = "double_quote"
                current.append(char)
            elif char == "-" and next_char == "-":
                state = "line_comment"
                current.extend((char, next_char))
                index += 1
            elif char == "/" and next_char == "*":
                state = "block_comment"
                current.extend((char, next_char))
                index += 1
            elif char == "$":
                closing = sql.find("$", index + 1)
                candidate = sql[index : closing + 1] if closing != -1 else ""
                tag_body = candidate[1:-1]
                if candidate and (
                    not tag_body
                    or (
                        (tag_body[0].isalpha() or tag_body[0] == "_")
                        and all(part.isalnum() or part == "_" for part in tag_body)
                    )
                ):
                    dollar_tag = candidate
                    state = "dollar_quote"
                    current.append(candidate)
                    index = closing
                else:
                    current.append(char)
            elif char == ";":
                statement = "".join(current).strip()
                if statement:
                    statements.append(statement)
                current = []
            else:
                current.append(char)
        elif state == "single_quote":
            current.append(char)
            if char == "'" and next_char == "'":
                current.append(next_char)
                index += 1
            elif char == "'":
                state = "normal"
        elif state == "double_quote":
            current.append(char)
            if char == '"' and next_char == '"':
                current.append(next_char)
                index += 1
            elif char == '"':
                state = "normal"
        elif state == "line_comment":
            current.append(char)
            if char == "\n":
                state = "normal"
        elif state == "block_comment":
            current.append(char)
            if char == "*" and next_char == "/":
                current.append(next_char)
                index += 1
                state = "normal"
        elif state == "dollar_quote":
            if sql.startswith(dollar_tag, index):
                current.append(dollar_tag)
                index += len(dollar_tag) - 1
                state = "normal"
                dollar_tag = ""
            else:
                current.append(char)
        index += 1

    if state in {"single_quote", "double_quote", "block_comment", "dollar_quote"}:
        raise ValueError(f"unterminated SQL construct: {state}")
    statement = "".join(current).strip()
    if statement:
        statements.append(statement)
    return statements


def run_sql_file(filename: str) -> str:
    """Execute a SQL file statement-by-statement; return sha256 hex digest."""
    path = MIGRATION_DIR / filename
    sql = path.read_text(encoding="utf-8")
    checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    bind = op.get_bind()
    for statement in split_sql(sql):
        bind.execute(text(statement))
    return checksum


def expected_migration_checksum(version: str) -> str:
    path = MIGRATION_DIR / f"{version}_up.sql"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checksum_mismatches(rows: Iterable[tuple[str, str]]) -> list[str]:
    mismatches = []
    for version, recorded_checksum in rows:
        path = MIGRATION_DIR / f"{version}_up.sql"
        if not path.exists():
            mismatches.append(version)
            continue
        if expected_migration_checksum(version) != recorded_checksum:
            mismatches.append(version)
    return mismatches


def record_schema_migration(version: str, checksum: str) -> None:
    """Keep the legacy schema_migrations ledger in sync for readiness checks."""
    bind = op.get_bind()
    bind.execute(
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
    bind.execute(
        text(
            """
            INSERT INTO schema_migrations (version, checksum)
            VALUES (:version, :checksum)
            ON CONFLICT (version) DO NOTHING
            """
        ),
        {"version": version, "checksum": checksum},
    )
    recorded = bind.execute(
        text("SELECT checksum FROM schema_migrations WHERE version = :version"),
        {"version": version},
    ).scalar_one()
    if recorded != checksum:
        raise RuntimeError(
            f"已应用迁移 {version} 的 checksum 与当前 SQL 不一致；"
            "禁止修改已发布迁移，请新增 revision"
        )


def delete_schema_migration(version: str) -> None:
    bind = op.get_bind()
    bind.execute(
        text("DELETE FROM schema_migrations WHERE version = :version"),
        {"version": version},
    )


def apply_named_sql_migration(version: str) -> None:
    checksum = run_sql_file(f"{version}_up.sql")
    record_schema_migration(version, checksum)


def revert_named_sql_migration(version: str) -> None:
    run_sql_file(f"{version}_down.sql")
    delete_schema_migration(version)
