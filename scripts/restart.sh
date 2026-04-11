#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "=== Restarting services ==="
docker compose up -d --build --force-recreate
echo ""
echo "=== Đã restart ==="
echo "Xem log: ./scripts/status.sh"
