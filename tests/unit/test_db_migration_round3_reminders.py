"""Round 3 fixture-from-old: a reminder row inserted with pre-round schema
is still readable, due-listable, and mark-done-able via ReminderRepo."""
from datetime import datetime, timedelta, timezone

import aiosqlite

from src.db import _init_schema
from src.repositories.reminder_repo import ReminderRepo


async def test_pre_round_reminder_still_actionable_via_repo(tmp_path):
    db_path = tmp_path / "history.db"
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    try:
        await _init_schema(conn)
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(
            sep=" ", timespec="seconds",
        )
        await conn.execute(
            "INSERT INTO reminders "
            "(boss_chat_id, target_chat_id, target_name, content, remind_at, "
            " status, source_chat_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("boss-1", None, "", "old reminder", past, "pending", None),
        )
        await conn.commit()

        repo = ReminderRepo(conn)

        due = await repo.get_due()
        assert any(r["content"] == "old reminder" for r in due)

        rid = due[0]["id"]
        await repo.mark_done(rid)

        async with conn.execute(
            "SELECT status FROM reminders WHERE id = ?", (rid,)
        ) as cur:
            row = await cur.fetchone()
        assert row["status"] == "done"
    finally:
        await conn.close()
