"""DataErasure (PDPL): erase_group đúng scope, erase_boss sạch + anonymize.

Spec: docs/superpowers/specs/2026-07-02-compliance-erasure-retention-design.md
"""

from __future__ import annotations

import pytest

from src.services.data_erasure import DataErasure


async def _boss(pool, email):
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO users (email, name, role) VALUES ($1, 'Sếp Erase', 'boss') RETURNING id",
            email,
        )


async def _seed_group(pool, boss_id, chat_id, provider="zalo"):
    """Một nhóm đầy đủ: group_notes + messages + knowledge + reminder."""
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO group_notes (boss_id, provider, chat_id, group_name) "
            "VALUES ($1,$2,$3,$3)", boss_id, provider, chat_id)
        mid = await c.fetchval(
            "INSERT INTO messages (boss_id, provider, chat_id, chat_type, provider_msg_id, "
            "text, ts) VALUES ($1,$2,$3,'group',$3||'-m1','giao việc A', NOW()) RETURNING id",
            boss_id, provider, chat_id)
        kid = await c.fetchval(
            "INSERT INTO knowledge_items (boss_id, provider, chat_id, kind, title, content, "
            "status) VALUES ($1,$2,$3,'decision','Việc A','Việc A giao cho An','active') "
            "RETURNING id", boss_id, provider, chat_id)
        await c.execute(
            "INSERT INTO knowledge_provenance (knowledge_item_id, message_id) VALUES ($1,$2)",
            kid, mid)
        await c.execute(
            "INSERT INTO scheduled_reminders (boss_id, text, due_at, scope, provider, chat_id, "
            "status, created_by_op) VALUES ($1,'nhắc A',NOW() + interval '1 day','group',$2,$3,"
            "'pending','test')", boss_id, provider, chat_id)


async def _count(pool, table, boss_id, chat_id=None):
    q = f"SELECT count(*) FROM {table} WHERE boss_id=$1"
    args = [boss_id]
    if chat_id is not None:
        q += " AND chat_id=$2"
        args.append(chat_id)
    async with pool.acquire() as c:
        return await c.fetchval(q, *args)


@pytest.mark.asyncio
async def test_erase_group_cleans_only_that_group(clean_db):
    boss = await _boss(clean_db, "er1@x.test")
    other_boss = await _boss(clean_db, "er1b@x.test")
    await _seed_group(clean_db, boss, "g-target")
    await _seed_group(clean_db, boss, "g-keep")
    await _seed_group(clean_db, other_boss, "g-target")  # nhóm cùng chat_id, boss khác

    counts = await DataErasure(clean_db).erase_group(boss, "zalo", "g-target")

    assert counts["messages"] == 1
    assert counts["knowledge_items"] == 1
    assert counts["group_notes"] == 1
    assert counts["scheduled_reminders"] == 1
    for table in ("messages", "knowledge_items", "group_notes", "scheduled_reminders"):
        assert await _count(clean_db, table, boss, "g-target") == 0, table
        assert await _count(clean_db, table, boss, "g-keep") == 1, table  # nhóm khác còn
        assert await _count(clean_db, table, other_boss, "g-target") == 1, table  # boss khác còn


@pytest.mark.asyncio
async def test_erase_boss_cleans_everything_and_anonymizes(clean_db):
    boss = await _boss(clean_db, "er2@x.test")
    other = await _boss(clean_db, "er2-other@x.test")
    await _seed_group(clean_db, boss, "g-a")
    await _seed_group(clean_db, boss, "g-b")
    await _seed_group(clean_db, other, "g-o")
    async with clean_db.acquire() as c:
        acc = await c.fetchval(
            "INSERT INTO bot_accounts (provider, provider_user_id, account_kind, ownership, "
            "owner_boss_id) VALUES ('zalo', $1, 'personal', 'boss_owned', $2) RETURNING id",
            f"erase-acc-{boss}", boss)
        await c.execute(
            "INSERT INTO bot_account_assignments (boss_id, provider, bot_account_id, "
            "assignment_kind, status) VALUES ($1,'zalo',$2,'boss_owned','active')", boss, acc)
        await c.execute(
            "INSERT INTO account_links (boss_id, provider, provider_user_id) "
            "VALUES ($1,'zalo',$2)", boss, f"main-{boss}")

    counts = await DataErasure(clean_db).erase_boss(boss)

    assert counts["group_notes"] == 2
    assert counts["bot_accounts"] == 1
    assert counts["users_anonymized"] == 1
    for table in ("messages", "knowledge_items", "group_notes", "scheduled_reminders",
                  "account_links", "bot_account_assignments"):
        assert await _count(clean_db, table, boss) == 0, table
    async with clean_db.acquire() as c:
        row = await c.fetchrow("SELECT email, name, api_keys_enc FROM users WHERE id=$1", boss)
        n_acc = await c.fetchval(
            "SELECT count(*) FROM bot_accounts WHERE owner_boss_id=$1", boss)
    assert row["email"] == f"erased-{boss}@erased.invalid"
    assert row["name"] is None and row["api_keys_enc"] is None
    assert n_acc == 0
    # Boss khác không bị đụng
    assert await _count(clean_db, "group_notes", other) == 1


@pytest.mark.asyncio
async def test_erase_group_via_api_deletes_data(client, logged_in_boss, clean_db):
    from src.web.security import CSRF_COOKIE

    boss = logged_in_boss.boss_id
    await _seed_group(clean_db, boss, "g-api", provider="web")
    async with clean_db.acquire() as c:
        gid = await c.fetchval(
            "SELECT id FROM group_notes WHERE boss_id=$1 AND chat_id='g-api'", boss)

    client.cookies.set(CSRF_COOKIE, "csrf-erase")
    r = client.delete(f"/api/v1/admin/groups/{gid}", headers={"X-CSRF-Token": "csrf-erase"})
    assert r.status_code == 204
    for table in ("messages", "knowledge_items", "group_notes"):
        assert await _count(clean_db, table, boss, "g-api") == 0, table
