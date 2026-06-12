#!/usr/bin/env bash
# Cài dependencies cho Zalo bridge (zca-js) — bắt buộc trước khi dùng đăng nhập QR.
set -euo pipefail

cd "$(dirname "$0")/../src/channels/zalo/bridge"
npm install --no-fund --no-audit

echo "Zalo bridge sẵn sàng."
echo "Đăng nhập QR thực hiện ngay trên web:"
echo "  - Superadmin > Tài khoản bot > (chọn account) > Kết nối"
echo "  - Admin > Kênh kết nối > Zalo (boss tự kết nối acc phụ)"
