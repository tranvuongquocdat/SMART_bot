#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "=== Setup AI Trợ Lý Giám Đốc ==="

# Tạo .env từ example nếu chưa có
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[+] Đã tạo .env từ .env.example"
    echo "[!] Hãy mở .env và điền các API keys trước khi start"
else
    echo "[=] .env đã tồn tại, bỏ qua"
fi

# Tạo thư mục data
mkdir -p data
echo "[+] Thư mục data/ OK"

# Build docker images
echo "[*] Building Docker images..."
docker compose build

echo ""
echo "=== Setup xong ==="
echo "Bước tiếp: điền API keys vào .env rồi chạy ./scripts/start.sh"
