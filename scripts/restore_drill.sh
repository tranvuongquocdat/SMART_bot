#!/usr/bin/env bash
# DIỄN TẬP restore: backup chưa restore thử = CHƯA có backup.
# Restore bản pg dump mới nhất vào DB scratch, so sánh số dòng vài bảng lõi
# với DB đang chạy, rồi dọn. Không đụng DB production.
#
# Chạy định kỳ (vd sau mỗi lần backup đầu tuần):  bash scripts/restore_drill.sh
# Restore THẬT (sự cố): như dưới nhưng vào DB chính sau khi dừng app —
# xem RUNBOOK DEPLOY trong docs/architecture/system-design.md.
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-backups}"
PG_CONTAINER="${PG_CONTAINER:-docker-postgres-1}"
PG_USER="${PG_USER:-smart}"
PG_DB="${PG_DB:-smart_bot}"
DRILL_DB="${PG_DB}_drill"

LATEST="$(ls -1t "$BACKUP_DIR/pg-$PG_DB"-*.dump 2>/dev/null | head -1)"
[ -n "$LATEST" ] || { echo "Không có bản dump nào trong $BACKUP_DIR — chạy scripts/backup.sh trước."; exit 1; }
echo "drill với: $LATEST"

docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d postgres -qc "DROP DATABASE IF EXISTS $DRILL_DB"
docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d postgres -qc "CREATE DATABASE $DRILL_DB"
docker exec -i "$PG_CONTAINER" pg_restore -U "$PG_USER" -d "$DRILL_DB" --no-owner < "$LATEST"

FAIL=0
for t in users messages knowledge_items group_notes scheduled_reminders subscription_requests; do
  live=$(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc "SELECT count(*) FROM $t")
  drill=$(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$DRILL_DB" -tAc "SELECT count(*) FROM $t")
  # live có thể đã nhích lên sau lúc dump — chỉ bắt lỗi khi drill = 0 mà live > 0
  if [ "$drill" -eq 0 ] && [ "$live" -gt 0 ]; then
    echo "[FAIL] $t: drill=0, live=$live"; FAIL=1
  else
    echo "[OK]   $t: drill=$drill (live=$live)"
  fi
done

docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d postgres -qc "DROP DATABASE $DRILL_DB"
[ "$FAIL" -eq 0 ] && echo "DRILL PASS — bản dump restore được." || { echo "DRILL FAIL"; exit 1; }
