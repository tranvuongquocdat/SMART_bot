"""Round 2 fixture-from-old: pre-round memberships rows survive _init_schema
and remain queryable through MembershipRepo."""
import aiosqlite

from src.db import _init_schema
from src.repositories.membership_repo import MembershipRepo


async def test_pre_round_memberships_still_readable_via_repo(tmp_path):
    db_path = tmp_path / "history.db"
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    try:
        await _init_schema(conn)
        await conn.execute(
            "INSERT INTO bosses "
            "(chat_id, name, lark_base_token, lark_table_people, "
            " lark_table_tasks, lark_table_projects, lark_table_ideas, email) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("boss-1", "Boss", "b", "p", "t", "pj", "i", ""),
        )
        await conn.execute(
            "INSERT INTO memberships "
            "(chat_id, boss_chat_id, person_type, name, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("u1", "boss-1", "member", "Alice", "active"),
        )
        await conn.execute(
            "INSERT INTO memberships "
            "(chat_id, boss_chat_id, person_type, name, status) "
            "VALUES (?, ?, ?, ?, ?)",
            ("u2", "boss-1", "partner", "Bob", "active"),
        )
        await conn.commit()

        repo = MembershipRepo(conn)

        got = await repo.get("u1", "boss-1")
        assert got["name"] == "Alice"

        for_user = await repo.list_for_user("u2")
        assert any(m["name"] == "Bob" for m in for_user)

        for_boss = await repo.list_for_boss("boss-1")
        assert len(for_boss) == 2
    finally:
        await conn.close()
