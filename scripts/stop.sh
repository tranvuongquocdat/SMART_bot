#!/bin/bash
# Stop the local uvicorn app. By default leaves Qdrant running (you usually
# want to keep it up across restarts). Pass --all to also stop Qdrant.
set -e
cd "$(dirname "$0")/.."

PID_FILE=data/.app.pid

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        # Wait up to 5s for graceful shutdown, then force.
        for _ in $(seq 1 5); do
            kill -0 "$PID" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID" 2>/dev/null || true
            echo "✓ App force-killed (pid=$PID)"
        else
            echo "✓ App stopped (pid=$PID)"
        fi
    else
        echo "App not running (stale pid=$PID)"
    fi
    rm -f "$PID_FILE"
else
    # No pid file — try to find uvicorn for this project anyway.
    if pgrep -fa "uvicorn src.main:app" >/dev/null; then
        pkill -f "uvicorn src.main:app" || true
        echo "✓ App stopped (matched by name, no pid file)"
    else
        echo "App not running."
    fi
fi

if [ "$1" = "--all" ]; then
    echo "→ docker compose down qdrant"
    docker compose down >/dev/null
    echo "✓ Qdrant stopped"
fi
