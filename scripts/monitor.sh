#!/usr/bin/env bash
# Healthcheck + alert khi ĐỔI TRẠNG THÁI (không spam mỗi 5 phút).
# Cron:  */5 * * * *  bash /path/to/scripts/monitor.sh
# Alert qua Telegram nếu set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (env hoặc
# ~/.smartbot-monitor.env); không có thì chỉ ghi log ~/.smartbot-monitor.log.
set -uo pipefail

APP_URL="${APP_URL:-http://localhost:8000}"
STATE_FILE="${STATE_FILE:-$HOME/.smartbot-monitor.state}"
LOG_FILE="${LOG_FILE:-$HOME/.smartbot-monitor.log}"
[ -f "$HOME/.smartbot-monitor.env" ] && . "$HOME/.smartbot-monitor.env"

BODY="$(curl -fsS -m 10 "$APP_URL/healthz" 2>/dev/null)" || BODY=""
if [ -n "$BODY" ] && ! echo "$BODY" | grep -q false; then
  STATUS="up"
else
  STATUS="down"
fi

PREV="$(cat "$STATE_FILE" 2>/dev/null || echo unknown)"
echo "$STATUS" > "$STATE_FILE"
echo "$(date '+%F %T') $STATUS ${BODY:-no-response}" >> "$LOG_FILE"

if [ "$STATUS" != "$PREV" ] && [ "$PREV" != "unknown" ]; then
  MSG="[smart-bot] $([ "$STATUS" = up ] && echo 'ĐÃ HỒI PHỤC' || echo 'SỰ CỐ') — healthz: ${BODY:-không phản hồi} ($(date '+%F %T'))"
  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    curl -fsS -m 10 "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
      -d chat_id="$TELEGRAM_CHAT_ID" --data-urlencode text="$MSG" > /dev/null || true
  fi
  echo "$(date '+%F %T') ALERT: $MSG" >> "$LOG_FILE"
fi
