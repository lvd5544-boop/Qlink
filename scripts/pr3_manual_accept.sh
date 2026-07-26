#!/usr/bin/env bash
# PR3 一键人工验收：自动播种数据并对运行中的 API 做边界断言。
#
# 前置：后端已启动（默认 http://localhost:8000），且与 backend/.env 的 DATABASE_URL 一致。
#
# 用法：
#   ./scripts/pr3_manual_accept.sh
#   API_BASE=http://127.0.0.1:8000 ./scripts/pr3_manual_accept.sh
#   ./scripts/pr3_manual_accept.sh --api http://localhost:8000

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
API_BASE="${API_BASE:-http://localhost:8000}"

if [[ ! -x "$BACKEND/.venv/bin/python" ]]; then
  echo "找不到 $BACKEND/.venv/bin/python"
  echo "请先：cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo "检查 API 是否可达：$API_BASE/health"
if ! curl -sf "$API_BASE/health" >/dev/null; then
  echo "无法连接 $API_BASE"
  echo "请先启动后端，例如："
  echo "  cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000"
  echo "或：docker compose up -d"
  exit 1
fi

echo "开始 PR3 验收..."
exec "$BACKEND/.venv/bin/python" "$BACKEND/scripts/pr3_manual_accept.py" --api "$API_BASE" "$@"
