#!/bin/bash
# Stop the local app (uvicorn on :8000) and the docker infra (postgres + qdrant).
# Idempotent: missing process / down containers are not errors.

set -u

# Kill anything bound to the app port.
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
else
  echo "no process on :$PORT"
fi

# Stop docker infra.
docker compose -f docker/docker-compose.yml stop postgres qdrant
