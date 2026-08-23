#!/usr/bin/env bash
set -euo pipefail

if [[ "${CONFIRM_RESTORE:-}" != "RESTORE_AND_OVERWRITE" ]]; then
  echo "Restore replaces the current database and uploads."
  echo "Re-run with CONFIRM_RESTORE=RESTORE_AND_OVERWRITE."
  exit 2
fi

if [[ $# -ne 1 ]]; then
  echo "Usage: CONFIRM_RESTORE=RESTORE_AND_OVERWRITE $0 backups/<timestamp>"
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="$(cd "$1" && pwd)"
cd "$ROOT"

if [[ -f "$SOURCE/STATUS" ]] && [[ "$(tr -d '[:space:]' <"$SOURCE/STATUS")" != "complete" ]]; then
  echo "Refusing an incomplete backup: $SOURCE" >&2
  exit 1
fi

if [[ ! -f "$SOURCE/evidence-vault.tar.gz" ]] && \
   [[ "${ALLOW_LEGACY_BACKUP_WITHOUT_EVIDENCE_VAULT:-}" != "I_ACCEPT_MISSING_EVIDENCE" ]]; then
  echo "This legacy backup has no evidence-vault archive." >&2
  echo "Restore is blocked to prevent silent evidence loss." >&2
  echo "If that loss is understood, set ALLOW_LEGACY_BACKUP_WITHOUT_EVIDENCE_VAULT=I_ACCEPT_MISSING_EVIDENCE." >&2
  exit 2
fi

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

(
  cd "$SOURCE"
  shasum -a 256 -c SHA256SUMS
)

compose stop backend worker scheduler
compose exec -T db sh -c \
  'psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --command "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"'
compose exec -T db sh -c \
  'pg_restore --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --no-owner --no-privileges' \
  <"$SOURCE/database.dump"

compose run --rm --no-deps backend \
  sh -c "find /data/uploads -mindepth 1 -delete"
compose run --rm --no-deps -T backend \
  tar -C /data/uploads -xzf - <"$SOURCE/uploads.tar.gz"

compose run --rm --no-deps backend \
  sh -c "find /data/evidence-vault -mindepth 1 -delete"
if [[ -f "$SOURCE/evidence-vault.tar.gz" ]]; then
  compose run --rm --no-deps -T backend \
    tar -C /data/evidence-vault -xzf - <"$SOURCE/evidence-vault.tar.gz"
fi

compose up -d migration backend worker scheduler

# Nginx resolves the Compose service name when it starts. Recreate the frontend
# after the backend restart so it cannot keep proxying to the old container IP.
compose up -d --force-recreate frontend

ready=false
for _ in {1..20}; do
  if compose exec -T frontend \
    wget -q -O - http://127.0.0.1/api/ready >/dev/null; then
    ready=true
    break
  fi
  sleep 2
done

if [[ "$ready" != "true" ]]; then
  echo "Restore finished, but the public /api/ready route is unavailable." >&2
  exit 1
fi

echo "Restore completed from: $SOURCE"
