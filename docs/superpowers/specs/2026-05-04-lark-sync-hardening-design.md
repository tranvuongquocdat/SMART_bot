# Lark sync hardening — Reminders & Notes

**Date:** 2026-05-04
**Status:** Approved (design phase)
**Scope:** Plan A from risk audit — close DB↔Lark drift gaps for reminders and notes; add bidirectional sync incl. manual Lark edits; replace fire-and-forget with inline await + retry.

## Problem

Audit of write paths found two classes of silent data drift:

1. **DB-only writes that never reach Lark.** `note_service.update_note` / `append_note` only write SQLite + Qdrant. `sync_note_to_lark` exists in `lark_client.py` but is never called. `reminder_service.update_reminder` and `delete_reminder` also skip Lark.
2. **Fire-and-forget Lark writes that fail silently.** `reminder_service.create_reminder` uses `asyncio.create_task(lark.sync_reminder_to_lark(...))`. If Lark is down, the reminder lives in DB but never appears in Lark; no retry, no surface.
3. **Reverse sync (Lark → DB) is incomplete.** Scheduler mirrors only `Nội dung` + `Trạng thái` for reminders. Manual edits to `Thời gian nhắc` in Lark are ignored — scheduler still fires at the original time. Manual deletion in Lark does not cancel the DB reminder. Manual additions in Lark are not pulled into DB at all. Notes have no reverse sync.
4. **`search_records` is paged at 100 with no follow-on.** Once a tenant has > 100 reminders / notes / tasks, anything past row 100 is invisible — including the existence check inside `sync_reminder_to_lark`, which can produce duplicate Lark rows.

User intent: **Lark is the source of truth.** No DB-only writes; manual Lark edits must be detected and reflected.

## Non-goals

Out of scope for this spec — tracked separately:

- Task / Project reverse-sync expansion (audit items 5-6).
- Cross-channel identity (Lark People `Type` / `Channel`) — audit item 8.
- Outbox-pattern queue. Decided against: codebase already inline-awaits Lark for tasks/projects; outbox defers failure visibility, opposite of "Lark is source of truth".
- Approval timeout sweeping (audit item 9).
- Zalo inbound idempotency (audit item 10).

## Architecture decisions

| Decision | Choice | Rationale |
|---|---|---|
| Sync timing | Inline `await` after DB write | Matches existing pattern for tasks/projects; surfaces failures immediately to the user |
| Transient errors | Helper `with_retry(fn, attempts=2, backoff=0.5s)` for httpx network errors and HTTP 5xx | Covers transient blips without a queue. Lark business errors (`code != 0`) are not retried. |
| Permanent failure after retry | Keep DB row, return tool message stating "saved locally, will sync later"; periodic reconciler re-pushes | Avoid losing user's work; avoid pretending success |
| Reverse-sync conflict | **Lark wins** on content / timing fields | Stated intent: Lark is source of truth |
| Manual additions in Lark | Bot pulls them into DB on next reverse-sync pass | User can author reminders/notes directly in Lark UI |
| Lark deletion | Tombstone DB (reminders → `status='cancelled'`; notes → delete row + Qdrant point) | Match user expectation: "deleted in Lark" = "gone" |
| Pagination | Loop `page_token` until `has_more=false`, hard cap 5000 records | Prevent silent truncation; cap protects against runaway tenants |

## Schema changes

Two new nullable columns, added in `_migrate_schema` per project convention (no ad-hoc DDL):

```sql
ALTER TABLE reminders ADD COLUMN lark_record_id TEXT;
ALTER TABLE notes     ADD COLUMN lark_record_id TEXT;
```

Used by:
- The reconciler to identify rows that have not yet been pushed to Lark (`lark_record_id IS NULL`).
- The reverse-sync pass to identify DB rows whose Lark counterpart vanished (tombstone candidates).

## Outbound sync (DB → Lark)

### Reminders — `src/services/reminder_service.py`

**`create_reminder`**
1. Parse local time → UTC; insert DB row.
2. `await lark_client.with_retry(lambda: sync_reminder_to_lark(...))`.
3. On success: write `lark_record_id` back to DB.
4. On failure after retries: log error; tool returns `"Đã tạo nhắc nhở #{id}: ... (đang chờ đồng bộ Lark)"`. Reconciler will retry on next 30s pass.

**`update_reminder`**
1. Apply DB update.
2. Re-read DB row.
3. `await lark_client.with_retry(lambda: sync_reminder_to_lark(...))` — upserts by `SQLite ID`.
4. On failure: tool returns `"Đã cập nhật nhắc nhở #{id} (đang chờ đồng bộ Lark)"`.

**`delete_reminder`** — Lark first, DB second (atomic-ish)
1. Look up `lark_record_id` from DB.
2. If `lark_record_id` present: `await lark_client.with_retry(lambda: delete_record(...))`. If this fails, **abort**: return tool message "Lark đang lỗi, chưa xoá được #{id} — anh thử lại sau." DB row stays intact; user can retry.
3. Lark delete succeeded (or no `lark_record_id` to delete): delete DB row.

Rationale: this is the one case where "leave DB row + reconcile later" produces user-visible inconsistency (user thinks deleted, but it still fires). Surface the failure and force a retry instead.

### Notes — `src/services/note_service.py`

**`update_note`** and **`append_note`**: identical pattern.
1. Compute new content (overwrite or append).
2. `await db.update_note(...)`.
3. `await lark_client.with_retry(lambda: sync_note_to_lark(...))` — upserts by `SQLite ID`.
4. Persist `lark_record_id`.
5. Existing `asyncio.create_task(_embed_note(...))` for Qdrant stays fire-and-forget — Qdrant is a derived index, not master.

No `delete_note` tool exists today. Out of scope to add one; reverse-sync handles deletes-in-Lark.

### Retry helper — `src/infrastructure/lark_client.py`

```python
async def with_retry(coro_factory, attempts: int = 2, backoff: float = 0.5):
    """Retry httpx network errors and HTTP 5xx. Lark business errors (code != 0)
    raise on first occurrence — those are deterministic and not worth retrying."""
```

Implementation:
- Catch `httpx.RequestError` and `httpx.HTTPStatusError` where `response.status_code >= 500`.
- Sleep `backoff * (2 ** attempt)` between tries.
- Re-raise the last exception if all attempts fail.

## Reverse sync (Lark → DB)

Replace `_sync_lark_to_sqlite` body with two cooperating blocks. Reminders run every 30s (existing cadence — user-visible timing matters). Notes run every 5 min (lower cadence — content changes are less time-sensitive).

### Reminder reverse-sync (every 30s)

For each boss with `lark_table_reminders` configured:

1. `lark_records = await search_records(base, table_reminders)` — paginated.
2. Build `seen_lark_ids: set[str]` from `lark_records[*].record_id`.
3. **Lark → DB updates and inserts:**
   - For rows with `SQLite ID`: update DB `content`, `status`, and `remind_at` (parse `Thời gian nhắc` as local → UTC). Skip if parse fails (log warning).
   - For rows without `SQLite ID`: pull `Nội dung`, `Thời gian nhắc`, `Trạng thái`, `Người nhận`. If parse fails, log + skip. On success: insert DB row, then call `sync_reminder_to_lark` to write `SQLite ID` back to that Lark row.
4. **Tombstone vanished:** `SELECT id FROM reminders WHERE boss_chat_id=? AND lark_record_id IS NOT NULL AND lark_record_id NOT IN (seen_lark_ids) AND status='pending'` → update those rows to `status='cancelled'`.
5. **Reconcile push-failures:** `SELECT * FROM reminders WHERE boss_chat_id=? AND lark_record_id IS NULL AND status='pending'` → for each, call `sync_reminder_to_lark`; on success persist returned `record_id`.

### Note reverse-sync (every 5 min)

Same structure as reminders, with note-specific fields:

1. Page-fetch all rows from `lark_table_notes`.
2. For rows with `SQLite ID`: `(Loại, Ref ID)` is the natural key. If Lark `Nội dung` differs from DB content → DB := Lark, then re-embed Qdrant.
3. For rows without `SQLite ID`: insert DB note keyed by `(Loại, Ref ID)`, then write `SQLite ID` back to Lark.
4. **Delete vanished:** DB notes with `lark_record_id NOT IN seen_lark_ids` → delete DB row, delete Qdrant point.
5. **Reconcile push-failures:** DB notes with `lark_record_id IS NULL` → push to Lark.

### Concurrency / race semantics

- **Bot edit + Lark user edit in the same 30s window:** next reverse-sync pass overwrites DB with Lark value. Acceptable per "Lark wins" policy.
- **Two concurrent reverse-sync passes** — guarded by APScheduler's default `max_instances=1` for each job. No additional locking needed.
- **A row created by the reverse-sync, then immediately edited again in Lark before SQLite ID is written back** — next pass will see it as "new" again and create a duplicate DB row. Mitigation: write SQLite ID back to Lark within the same loop iteration, before processing the next row. Acceptable residual risk.

## Pagination — `src/infrastructure/lark_client.py`

Replace the single-page implementation in `search_records`:

```python
async def search_records(base_token, table_id, filter_expr="") -> list[dict]:
    items: list[dict] = []
    page_token: str | None = None
    HARD_CAP = 5000
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        if filter_expr:
            params["filter"] = filter_expr
        # ... GET, raise_for_status, decode body
        items.extend({"record_id": r["record_id"], **r["fields"]} for r in body["data"].get("items", []))
        if len(items) >= HARD_CAP:
            logger.warning("search_records: hit hard cap %d for table %s", HARD_CAP, table_id)
            break
        if not body["data"].get("has_more"):
            break
        page_token = body["data"].get("page_token")
    return items
```

Same signature. All current callers benefit transparently.

## Test plan

New unit tests in `tests/`. Mock `lark_client._client` (httpx) to control responses.

| Test | Verifies |
|---|---|
| `test_lark_search_records_paginates` | Mocked 3-page response → returned list contains all rows from all pages |
| `test_lark_search_records_hard_cap` | 11 pages of 500 each → caller receives 5000, warning logged |
| `test_with_retry_recovers_on_5xx` | First call 503, second call 200 → no exception |
| `test_with_retry_does_not_retry_business_error` | Lark `code != 0` body → exception raised on first call |
| `test_with_retry_gives_up_after_attempts` | 3 consecutive 5xx → exception on attempts=2 |
| `test_create_reminder_persists_lark_record_id` | Mock Lark create returns `record_id` → DB row has it |
| `test_create_reminder_lark_failure_keeps_db_row` | Mock Lark fail → DB row exists with `lark_record_id IS NULL`, tool message includes "đang chờ đồng bộ" |
| `test_update_reminder_syncs_lark` | Update DB content → `sync_reminder_to_lark` is awaited with new content |
| `test_delete_reminder_removes_lark_row` | Delete with known `lark_record_id` → `delete_record` is called, then DB row gone |
| `test_delete_reminder_lark_failure_keeps_db_row` | Lark `delete_record` raises → DB row still present; tool message says retry later |
| `test_reverse_sync_pulls_time_change` | Lark `Thời gian nhắc` differs → DB `remind_at` updated to parsed UTC |
| `test_reverse_sync_tombstones_vanished` | DB has `lark_record_id=X`, Lark search omits X → DB row `status='cancelled'` |
| `test_reverse_sync_pulls_manual_add` | Lark row without SQLite ID → DB row created, `sync_reminder_to_lark` called to write back |
| `test_reverse_sync_reconciles_unsynced_db_row` | DB row with `lark_record_id IS NULL` → push to Lark, persist returned ID |
| `test_reverse_sync_skips_unparseable_time` | Lark `Thời gian nhắc = "không phải ngày"` → skip + log; sync loop continues |
| `test_note_update_syncs_lark` | `update_note` calls `sync_note_to_lark` with content |
| `test_note_reverse_sync_pulls_lark_edit` | Lark content differs → DB content updated, Qdrant re-embed scheduled |
| `test_note_reverse_sync_deletes_vanished` | DB note's `lark_record_id` not in Lark → DB row deleted, Qdrant point deleted |

## Migration / rollout

- The new `lark_record_id` columns are nullable. Existing reminders and notes start with `NULL` → first reverse-sync pass treats them as "needs reconcile push" and fills the column.
- No data backfill script needed; the reconcile path is the backfill.
- Risk: on a tenant with > 100 existing reminders / notes whose Lark rows were never created, the first reverse-sync after deploy will push all of them at once. Mitigation: cap reconcile work to 50 rows per pass per boss to spread load. (Implementation detail; out of design scope.)

## Failure modes after this change

| Scenario | Behavior |
|---|---|
| Lark down for 5 minutes during `create_reminder` | Tool returns "đang chờ đồng bộ Lark"; reconciler pushes within 30s of recovery |
| User deletes reminder in Lark UI | DB row marked `cancelled` within 30s; scheduler does not fire |
| User changes `Thời gian nhắc` in Lark | DB `remind_at` updated within 30s; scheduler fires at new time |
| User adds a note row directly in Lark | DB row created within 5 min; appears in subsequent `get_note` calls |
| Lark and bot edit same note in same 5-min window | Lark wins; bot's edit lost. Acceptable per stated policy. |
| Tenant grows past 100 reminders | All reminders sync correctly (pagination active) |
| Tenant grows past 5000 reminders | Hard cap warning logged; rows past 5000 invisible. Future work: raise cap or chunk by date. |

## Acceptance criteria

1. `update_note`, `append_note`, `update_reminder`, `delete_reminder` all reach Lark synchronously.
2. `create_reminder` uses `await` (no `asyncio.create_task`) for Lark sync.
3. `search_records` returns all rows up to 5000 — verified by integration test against a stub Lark with 250 rows.
4. Manual edit of `Thời gian nhắc` in Lark causes scheduler to fire at new time on next due check.
5. Manual deletion of reminder row in Lark prevents scheduler from firing it.
6. Manual addition of reminder row in Lark with valid time appears in `list_reminders` output within one reverse-sync cycle.
7. Lark API returning 503 → bot retries once and succeeds; user sees normal "Đã tạo" message with no error.
8. Lark API returning 503 twice → bot returns "đang chờ đồng bộ Lark"; reconciler completes within 60s of Lark recovery.
9. All new tests in `tests/` pass; existing tests still pass.
