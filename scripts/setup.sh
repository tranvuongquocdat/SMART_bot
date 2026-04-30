#!/bin/bash
# Interactive setup — đi từng phần, điền .env, build Docker.
# Chạy lại an toàn (idempotent): Enter để giữ giá trị hiện tại.
set -e

cd "$(dirname "$0")/.."

ENV_FILE=".env"

get_current() {
    [ -f "$ENV_FILE" ] || return
    grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-
}

# prompt KEY DESC [DEFAULT] [secret]
prompt() {
    local key="$1" desc="$2" default="${3:-}" secret="${4:-}"
    local current display input
    current=$(get_current "$key")
    [ -z "$current" ] && current="$default"

    if [ -n "$current" ]; then
        if [ "$secret" = "secret" ]; then
            display="${current:0:4}…(masked, len=${#current})"
        else
            display="$current"
        fi
        read -r -p "    $key — $desc
      [hiện tại: $display] Enter giữ, hoặc nhập mới: " input
        echo "${input:-$current}"
    else
        read -r -p "    $key — $desc
      nhập giá trị: " input
        echo "$input"
    fi
}

echo "=== Setup AI Secretary — interactive ==="
echo "(Enter để giữ giá trị hiện tại; chạy lại bất cứ lúc nào để sửa)"

echo
echo "[1/5] Telegram"
TELEGRAM_BOT_TOKEN=$(prompt TELEGRAM_BOT_TOKEN "Bot token (lấy từ @BotFather)" "" secret)

echo
echo "[2/5] Lark Suite"
LARK_APP_ID=$(prompt LARK_APP_ID "App ID")
LARK_APP_SECRET=$(prompt LARK_APP_SECRET "App Secret" "" secret)

echo
echo "[3/5] OpenAI"
OPENAI_API_KEY=$(prompt OPENAI_API_KEY "API key" "" secret)
OPENAI_CHAT_MODEL=$(prompt OPENAI_CHAT_MODEL "Chat model" "gpt-5.4")
OPENAI_EMBEDDING_MODEL=$(prompt OPENAI_EMBEDDING_MODEL "Embedding model" "text-embedding-3-small")

echo
echo "[4/5] Cohere"
COHERE_API_KEY=$(prompt COHERE_API_KEY "API key (rerank)" "" secret)

echo
echo "[5/5] App config"
QDRANT_URL=$(prompt QDRANT_URL "Qdrant URL" "http://qdrant:6333")
DB_PATH=$(prompt DB_PATH "SQLite path" "data/history.db")
TIMEZONE=$(prompt TIMEZONE "Timezone" "Asia/Ho_Chi_Minh")
RECENT_MESSAGES=$(prompt RECENT_MESSAGES "# tin gần nhất trong context" "8")
RAG_MESSAGES=$(prompt RAG_MESSAGES "# tin RAG trong context" "5")

# Giữ nguyên Zalo nếu đã setup; mặc định disabled.
ZALO_ENABLED=$(get_current ZALO_ENABLED); ZALO_ENABLED="${ZALO_ENABLED:-false}"
ZALO_NODE_PATH=$(get_current ZALO_NODE_PATH); ZALO_NODE_PATH="${ZALO_NODE_PATH:-node}"
ZALO_SESSION_PATH=$(get_current ZALO_SESSION_PATH)

TMP=$(mktemp)
cat > "$TMP" <<EOF
# Telegram
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN

# Lark Suite
LARK_APP_ID=$LARK_APP_ID
LARK_APP_SECRET=$LARK_APP_SECRET

# OpenAI
OPENAI_API_KEY=$OPENAI_API_KEY
OPENAI_CHAT_MODEL=$OPENAI_CHAT_MODEL
OPENAI_EMBEDDING_MODEL=$OPENAI_EMBEDDING_MODEL

# Cohere
COHERE_API_KEY=$COHERE_API_KEY

# Qdrant
QDRANT_URL=$QDRANT_URL

# App
DB_PATH=$DB_PATH
TIMEZONE=$TIMEZONE
RECENT_MESSAGES=$RECENT_MESSAGES
RAG_MESSAGES=$RAG_MESSAGES

# Zalo (chạy ./scripts/setup_zalo.sh để bật)
ZALO_ENABLED=$ZALO_ENABLED
ZALO_NODE_PATH=$ZALO_NODE_PATH
ZALO_SESSION_PATH=$ZALO_SESSION_PATH
EOF
mv "$TMP" "$ENV_FILE"
mkdir -p data
echo
echo "[+] .env saved"

echo
read -r -p "Build Docker images bây giờ? [Y/n]: " build
if [[ ! "$build" =~ ^[Nn]$ ]]; then
    docker compose build
fi

echo
echo "=== Setup xong ==="
echo "Bật Zalo:   ./scripts/setup_zalo.sh"
echo "Khởi động:  ./scripts/start.sh"
