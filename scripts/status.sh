#!/bin/bash
# Snapshot view: is the app process up, is Qdrant up, recent log tail.
cd "$(dirname "$0")/.."

PID_FILE=data/.app.pid
echo "=== App ==="
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        printf "  status: \033[32mRUNNING\033[0m  pid=%s\n" "$PID"
    else
        echo "  status: STOPPED (stale pid=$PID)"
    fi
else
    echo "  status: STOPPED"
fi

echo
echo "=== Health ==="
if curl -sf -m 2 http://localhost:24702/health 2>/dev/null; then
    echo
else
    echo "  /health không trả lời (app chưa boot xong, hoặc đã chết)"
fi

echo
echo "=== Qdrant ==="
if docker compose ps qdrant 2>/dev/null | tail -n +2 | grep -q "Up\|running"; then
    printf "  status: \033[32mRUNNING\033[0m\n"
else
    echo "  status: STOPPED"
fi

echo
echo "=== Logs (30 dòng cuối — full: ./scripts/logs.sh) ==="
if [ -f data/logs/app.log ]; then
    tail -n 30 data/logs/app.log
else
    echo "  data/logs/app.log chưa có"
fi
