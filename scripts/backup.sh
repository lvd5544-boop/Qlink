#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_ROOT="${BACKUP_DIR:-$ROOT/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$BACKUP_ROOT/$STAMP"

mkdir -p "$TARGET"
cd "$ROOT"

# A backup is restorable only after every artifact and checksum has been
# written. Operators and restore.sh can distinguish interrupted runs.
printf '2\n' >"$TARGET/FORMAT_VERSION"
printf 'incomplete\n' >"$TARGET/STATUS"

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

compose exec -T backend tar -C /data/evidence-vault -czf - . \
  >"$TARGET/evidence-vault.tar.gz"

(
  cd "$TARGET"
  shasum -a 256 FORMAT_VERSION database.dump uploads.tar.gz evidence-vault.tar.gz >SHA256SUMS
)

printf 'complete\n' >"$TARGET/STATUS"

echo "Backup created: $TARGET"
