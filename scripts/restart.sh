#!/bin/bash
# Restart the local app: stop old uvicorn, start infra, migrate, ensure SPA build, run uvicorn.
#   --build  force rebuild the frontend even if a build already exists
set -e
cd "$(dirname "$0")/.."

# Stop any process already bound to the app port (idempotent).
PORT=8000
PIDS=$(lsof -t -i :"$PORT" 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  echo "stopping uvicorn on :$PORT (pids: $PIDS)"
  kill $PIDS 2>/dev/null || true
  sleep 1
  STILL=$(lsof -t -i :"$PORT" 2>/dev/null || true)
  if [ -n "$STILL" ]; then
    echo "force-killing pids: $STILL"
    kill -9 $STILL 2>/dev/null || true
  fi
fi

docker compose -f docker/docker-compose.yml up -d postgres qdrant
uv run alembic upgrade head

# Build the SPA when missing (or when --build is passed).
if [ "${1:-}" = "--build" ] || [ ! -f src/web/static/app/index.html ]; then
  scripts/build_frontend.sh
fi

exec uv run uvicorn src.main:app --reload --host 0.0.0.0 --port "$PORT"
