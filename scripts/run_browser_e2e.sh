#!/usr/bin/env bash
# Local/CI helper: migrate + API + worker + frontend proxy, then Playwright.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/backend"
export DATABASE_URL="${DATABASE_URL:?DATABASE_URL required}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export REQUIRE_SCHEMA_VERSION="${REQUIRE_SCHEMA_VERSION:-1}"
export ENV="${ENV:-production}"
export SECRET_KEY="${SECRET_KEY:-ci-only-access-secret-at-least-32-bytes}"
export FIDELITY_PROOF_SECRET_KEY="${FIDELITY_PROOF_SECRET_KEY:-ci-only-proof-secret-at-least-32-bytes}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://127.0.0.1:4173}"
export MODEL_REQUIRED=false
export REQUIRE_BACKGROUND_HEARTBEATS=false
export EMPLOYER_INVITE_CODE="${EMPLOYER_INVITE_CODE:-e2e-employer-invite}"
export E2E_API_ORIGIN="${E2E_API_ORIGIN:-http://127.0.0.1:8000}"
export E2E_PORT="${E2E_PORT:-4173}"
export TESTING=0
export BACKGROUND_JOBS_INLINE=0
export UPLOAD_DIR="${UPLOAD_DIR:-${ROOT}/backend/uploads/e2e}"
mkdir -p "${UPLOAD_DIR}"

cd "${ROOT}/backend"
python scripts/migrate.py

uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
python -m app.background_jobs &
WORKER_PID=$!

cleanup() {
  kill "${API_PID}" "${WORKER_PID}" "${PROXY_PID:-}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

ready=0
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8000/ready >/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "${ready}" != "1" ]]; then
  echo "API failed to become ready" >&2
  exit 1
fi
curl -sf http://127.0.0.1:8000/ready >/dev/null

cd "${ROOT}/frontend"
npm run build
node e2e/proxy-server.mjs &
PROXY_PID=$!
sleep 1
npx playwright test
