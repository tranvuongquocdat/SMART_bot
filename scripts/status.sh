#!/bin/bash

cd "$(dirname "$0")/.."

echo "=== Container Status ==="
docker compose ps
echo ""

echo "=== Health Check ==="
curl -s http://localhost:8000/health 2>/dev/null || echo "App chưa chạy hoặc chưa sẵn sàng"
echo ""
echo ""

echo "=== Logs (50 dòng gần nhất) ==="
docker compose logs --tail 50
