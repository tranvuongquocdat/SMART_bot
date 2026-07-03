#!/usr/bin/env bash
# Backup Postgres (pg_dump custom format) + Qdrant (snapshot tải về local).
# Chạy tay hoặc cron hằng đêm:  0 2 * * *  bash /path/to/scripts/backup.sh
# Giữ 14 bản gần nhất. Restore: xem scripts/restore_drill.sh (diễn tập) +
# phần RUNBOOK DEPLOY trong docs/architecture/system-design.md.
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-backups}"
PG_CONTAINER="${PG_CONTAINER:-docker-postgres-1}"
PG_USER="${PG_USER:-smart}"
PG_DB="${PG_DB:-smart_bot}"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-smart_bot}"
KEEP=14

STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# --- Postgres ---------------------------------------------------------------
PG_OUT="$BACKUP_DIR/pg-$PG_DB-$STAMP.dump"
docker exec "$PG_CONTAINER" pg_dump -U "$PG_USER" -Fc "$PG_DB" > "$PG_OUT"
echo "pg dump: $PG_OUT ($(du -h "$PG_OUT" | cut -f1))"

# --- Qdrant snapshot ---------------------------------------------------------
SNAP_NAME="$(curl -fsS -X POST "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["name"])')"
QD_OUT="$BACKUP_DIR/qdrant-$QDRANT_COLLECTION-$STAMP.snapshot"
curl -fsS "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/$SNAP_NAME" -o "$QD_OUT"
# Xoá snapshot trong container sau khi đã tải về (khỏi đầy volume)
curl -fsS -X DELETE "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/$SNAP_NAME" > /dev/null
echo "qdrant snapshot: $QD_OUT ($(du -h "$QD_OUT" | cut -f1))"

# --- Prune: giữ $KEEP bản mỗi loại -------------------------------------------
for prefix in "pg-$PG_DB" "qdrant-$QDRANT_COLLECTION"; do
  ls -1t "$BACKUP_DIR/$prefix"-* 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm --
done
echo "done. $(ls -1 "$BACKUP_DIR" | wc -l | tr -d ' ') file(s) in $BACKUP_DIR/"
