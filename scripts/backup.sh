#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_ROOT="${BACKUP_DIR:-$ROOT/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$BACKUP_ROOT/$STAMP"

mkdir -p "$TARGET"
cd "$ROOT"

compose() {
  local args=(docker compose)
  if [[ -n "${COMPOSE_ENV_FILE:-}" ]]; then
    args+=(--env-file "$COMPOSE_ENV_FILE")
  fi
  if [[ -n "${COMPOSE_PROJECT_NAME:-}" ]]; then
    args+=(-p "$COMPOSE_PROJECT_NAME")
  fi
  "${args[@]}" "$@"
}

# Resolve database identity inside the container. `--env-file` controls
# Compose interpolation but does not export those values into this host shell.
compose exec -T db sh -c \
  'pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=custom' \
  >"$TARGET/database.dump"

compose exec -T backend tar -C /data/uploads -czf - . \
  >"$TARGET/uploads.tar.gz"

(
  cd "$TARGET"
  shasum -a 256 database.dump uploads.tar.gz >SHA256SUMS
)

echo "Backup created: $TARGET"
