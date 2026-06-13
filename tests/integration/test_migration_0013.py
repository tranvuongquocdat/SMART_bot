import pytest


@pytest.mark.asyncio
async def test_messages_unique_includes_boss_id(clean_db):
    async with clean_db.acquire() as c:
        cols = await c.fetch(
            """
            SELECT a.attname
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
            JOIN pg_attribute a ON a.attrelid = rel.oid AND a.attnum = k.attnum
            WHERE rel.relname = 'messages' AND con.contype = 'u'
            ORDER BY k.ord
            """
        )
    names = [r["attname"] for r in cols]
    assert names == ["boss_id", "provider", "chat_id", "provider_msg_id"]


@pytest.mark.asyncio
async def test_group_notes_gate_index_exists(clean_db):
    async with clean_db.acquire() as c:
        idx = await c.fetchval(
            "SELECT 1 FROM pg_indexes WHERE indexname = 'idx_group_notes_gate'"
        )
    assert idx == 1
