#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "=== Stopping services ==="
docker compose down
echo "=== Đã stop ==="
