"""Round 1 fixture-from-old: a pre-round boss row (raw SQL insert) must
remain readable through BossRepo after _init_schema runs. Guards the
boss free-function removal from accidentally breaking row layout."""
import aiosqlite

from src.db import _init_schema
from src.repositories.boss_repo import BossRepo


async def test_pre_round_boss_row_still_readable_via_repo(tmp_path):
    db_path = tmp_path / "history.db"
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    try:
        await _init_schema(conn)
        await conn.execute(
            "INSERT INTO bosses "
            "(chat_id, name, company, lark_base_token, lark_table_people, "
            " lark_table_tasks, lark_table_projects, lark_table_ideas, "
            " lark_table_reminders, lark_table_notes, email) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("boss-old-1", "Old Boss", "OldCo",
             "base-tok", "tp", "tt", "tprj", "ti", "tr", "tn",
             "old@example.com"),
        )
        await conn.commit()

        repo = BossRepo(conn)

        got = await repo.get("boss-old-1")
        assert got is not None
        assert got["name"] == "Old Boss"
        assert got["company"] == "OldCo"
        assert got["lark_base_token"] == "base-tok"

        listed = await repo.list_all()
        assert any(b["chat_id"] == "boss-old-1" for b in listed)
    finally:
        await conn.close()
