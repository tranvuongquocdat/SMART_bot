#!/bin/bash
# Set up Zalo bridge từng phần: check Node, npm install, login QR,
# auto-copy session vào data/zalo/, bật ZALO_ENABLED trong .env.
# Chạy lại an toàn để re-login khi session expired.
set -e

cd "$(dirname "$0")/.."

BRIDGE_DIR="src/channels/zalo_bridge"
SESSION_FILE="$BRIDGE_DIR/session.json"
DATA_DIR="data/zalo"
DATA_SESSION="$DATA_DIR/session.json"
ENV_FILE=".env"

echo "=== Setup Zalo bridge (single-account demo) ==="

# --- 1. Check Node ---------------------------------------------------------
echo
echo "[1/4] Kiểm tra Node…"
if ! command -v node >/dev/null 2>&1; then
    echo "[!] Chưa có Node. Cài Node 22 LTS từ https://nodejs.org/ rồi chạy lại."
    exit 1
fi
NODE_MAJOR=$(node -v | sed 's/v\([0-9]*\)\..*/\1/')
if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "[!] Node $(node -v) quá cũ. Cần Node 18+ (khuyến nghị 22)."
    exit 1
fi
echo "    Node $(node -v) OK"

# --- 2. npm install --------------------------------------------------------
echo
echo "[2/4] Cài deps cho bridge…"
if [ -d "$BRIDGE_DIR/node_modules" ]; then
    read -r -p "    node_modules đã có. Cài lại? [y/N]: " redo
    if [[ "$redo" =~ ^[Yy]$ ]]; then
        (cd "$BRIDGE_DIR" && npm install --omit=dev --no-audit --no-fund)
    else
        echo "    bỏ qua npm install"
    fi
else
    (cd "$BRIDGE_DIR" && npm install --omit=dev --no-audit --no-fund)
fi

# --- 3. QR login -----------------------------------------------------------
echo
echo "[3/4] Đăng nhập Zalo (QR)…"
DO_LOGIN=1
if [ -f "$SESSION_FILE" ]; then
    read -r -p "    session.json đã tồn tại. Login lại? [y/N]: " redo
    if [[ ! "$redo" =~ ^[Yy]$ ]]; then
        DO_LOGIN=0
        echo "    dùng session hiện có"
    fi
fi
if [ "$DO_LOGIN" -eq 1 ]; then
    echo "    Mở Zalo → Settings → Quét mã QR. Cửa sổ ảnh sẽ tự bật ra."
    if [ -f "$SESSION_FILE" ]; then
        (cd "$BRIDGE_DIR" && node login.js --force)
    else
        (cd "$BRIDGE_DIR" && node login.js)
    fi
fi

if [ ! -f "$SESSION_FILE" ]; then
    echo "[!] Không thấy $SESSION_FILE — login chưa hoàn tất?"
    exit 1
fi
echo "    [+] $SESSION_FILE OK"

# --- 4. Copy + cập nhật .env ----------------------------------------------
echo
echo "[4/4] Copy session vào $DATA_DIR/ và cập nhật .env…"
if [ ! -f "$ENV_FILE" ]; then
    echo "[!] Chưa có .env — chạy ./scripts/setup.sh trước."
    exit 1
fi

mkdir -p "$DATA_DIR"
cp "$SESSION_FILE" "$DATA_SESSION"
echo "    [+] $DATA_SESSION"

set_env() {
    local key="$1" value="$2"
    local tmp; tmp=$(mktemp)
    if grep -qE "^${key}=" "$ENV_FILE"; then
        awk -v k="$key" -v v="$value" '
            BEGIN { FS = "=" }
            $1 == k { print k "=" v; next }
            { print }
        ' "$ENV_FILE" > "$tmp"
        mv "$tmp" "$ENV_FILE"
    else
        rm -f "$tmp"
        echo "${key}=${value}" >> "$ENV_FILE"
    fi
}

set_env ZALO_ENABLED true
set_env ZALO_SESSION_PATH "$DATA_SESSION"
echo "    [+] .env: ZALO_ENABLED=true, ZALO_SESSION_PATH=$DATA_SESSION"

echo
echo "=== Zalo sẵn sàng ==="
echo "Khởi động lại app:  ./scripts/restart.sh"
echo "Login lại sau này:  ./scripts/setup_zalo.sh    (chọn 'y' khi hỏi login lại)"
