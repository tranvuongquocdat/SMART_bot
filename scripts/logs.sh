#!/bin/bash
# Tail the app log written by start.sh. Args:
#   (no args)       follow the live log
#   --prev          show the previous run's log instead (rotated by start.sh)
#   --qdrant        follow Qdrant container logs
#   -n N            initial lines to show before following (default 100)
cd "$(dirname "$0")/.."

LINES=100
TARGET=data/logs/app.log

while [ $# -gt 0 ]; do
    case "$1" in
        --prev)    TARGET=data/logs/app.log.prev; shift;;
        --qdrant)  docker compose logs -f --tail "$LINES" qdrant; exit;;
        -n)        LINES=$2; shift 2;;
        *)         echo "unknown flag: $1" >&2; exit 1;;
    esac
done

if [ ! -f "$TARGET" ]; then
    echo "$TARGET không tồn tại. App đã chạy bao giờ chưa? ./scripts/start.sh" >&2
    exit 1
fi

tail -n "$LINES" -F "$TARGET"
