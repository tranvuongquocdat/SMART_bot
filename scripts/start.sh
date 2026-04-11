#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "=== Starting services ==="

if [ ! -f .env ]; then
    echo "[!] Chưa có file .env. Chạy ./scripts/setup.sh trước."
    exit 1
fi

docker compose up -d --build
echo ""
echo "=== Đã start ==="
echo "App:    http://localhost:8000"
echo "Health: http://localhost:8000/health"
echo "Qdrant: http://localhost:6333"
echo ""
echo "Xem log: ./scripts/status.sh"
