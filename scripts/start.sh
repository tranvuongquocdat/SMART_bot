#!/bin/bash
# Hybrid run: Qdrant in docker, app local via uvicorn (detached, SSH-safe).
# - App keeps running after the SSH session disconnects (nohup + stdin
#   redirected from /dev/null, daemonized via `&`).
# - Logs go to data/logs/app.log — use ./scripts/logs.sh to tail.
# - PID stored in data/.app.pid so stop/restart can find it.
set -e
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "[!] Chưa có .env. Chạy ./scripts/setup.sh trước." >&2
    exit 1
fi
if [ ! -x .venv/bin/uvicorn ]; then
    echo "[!] .venv chưa cài uvicorn. Chạy: uv sync" >&2
    exit 1
fi

# 1. Qdrant (only service that needs docker)
echo "→ docker compose up -d qdrant"
docker compose up -d qdrant >/dev/null

# 2. Wait for Qdrant to accept connections (max 30s)
echo -n "→ waiting for Qdrant"
for _ in $(seq 1 30); do
    if curl -sf http://localhost:6333/readyz >/dev/null 2>&1 \
       || curl -sf http://localhost:6333/ >/dev/null 2>&1; then
        echo " — ready"
        break
    fi
    echo -n "."
    sleep 1
done

# 3. Check if app already running via pid file
mkdir -p data/logs
PID_FILE=data/.app.pid
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[!] App đã chạy (pid=$OLD_PID). Dùng ./scripts/restart.sh nếu muốn restart."
        exit 0
    fi
    rm -f "$PID_FILE"
fi

# 4. Spawn uvicorn detached. Survives SSH disconnect because:
#    - nohup ignores SIGHUP (sent on terminal close)
#    - stdin redirected from /dev/null so no controlling terminal
#    - stdout/stderr → log file, not the terminal
# Each run rotates the previous log to .prev so logs.sh can still grep history.
if [ -f data/logs/app.log ]; then
    mv data/logs/app.log data/logs/app.log.prev
fi
echo "→ starting uvicorn (detached)"
nohup .venv/bin/uvicorn src.main:app \
        --host 0.0.0.0 --port 24702 \
        --log-level info \
        </dev/null >data/logs/app.log 2>&1 &
echo $! >"$PID_FILE"
disown 2>/dev/null || true

sleep 1
if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "✓ App started, pid=$(cat $PID_FILE)"
    echo "  http://localhost:24702  ·  health: http://localhost:24702/health"
    echo "  logs: ./scripts/logs.sh   stop: ./scripts/stop.sh"
else
    echo "[!] App died ngay sau start — xem data/logs/app.log:" >&2
    tail -30 data/logs/app.log >&2
    rm -f "$PID_FILE"
    exit 1
fi
