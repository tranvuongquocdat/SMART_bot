"""activate() is the single chokepoint for status='active' membership writes."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.services import membership_service


@pytest_asyncio.fixture
async def setup_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    await conn.execute(
        "INSERT INTO bosses (chat_id, name, company, lark_base_token,"
        " lark_table_people, lark_table_tasks, lark_table_projects, lark_table_ideas) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("b1", "Boss", "Acme Co", "base", "ppl", "tsk", "prj", "idea"),
    )
    await conn.commit()
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_activate_writes_active_membership(setup_db, monkeypatch):
    monkeypatch.setattr(
        "src.services.membership_service.lark.create_record",
        AsyncMock(return_value={"record_id": "lark-1"}),
    )
    monkeypatch.setattr(
        "src.services.membership_service.telegram.send", AsyncMock(),
    )
    await membership_service.activate(
        chat_id="u1", boss_chat_id="b1",
        person_type="member", name="Alice",
        source="boss_add",
    )
    async with setup_db.execute(
        "SELECT status FROM memberships WHERE chat_id='u1' AND boss_chat_id='b1'"
    ) as cur:
        row = await cur.fetchone()
    assert row["status"] == "active"


async def test_activate_notifies_only_on_pending_transition(setup_db, monkeypatch):
    """When prior row was pending → notify. When prior row didn't exist → no notify."""
    monkeypatch.setattr(
        "src.services.membership_service.lark.create_record",
        AsyncMock(return_value={"record_id": "lark-1"}),
    )
    sent = AsyncMock()
    monkeypatch.setattr("src.services.membership_service.telegram.send", sent)

    await membership_service.activate(
        chat_id="u1", boss_chat_id="b1",
        person_type="member", name="Alice",
        source="boss_add",
    )
    assert sent.await_count == 0

    await setup_db.execute(
        "INSERT INTO memberships (chat_id, boss_chat_id, person_type, name, status) "
        "VALUES ('u2', 'b1', 'member', 'Bob', 'pending')"
    )
    await setup_db.commit()
    await membership_service.activate(
        chat_id="u2", boss_chat_id="b1",
        person_type="member", name="Bob",
        source="approval",
    )
    assert sent.await_count == 1
    notify_args = sent.await_args.args
    assert notify_args[0] == "u2"
    assert "approved" in notify_args[1].lower() or "Acme Co" in notify_args[1]


async def test_activate_upserts_lark_people_when_no_record_id(setup_db, monkeypatch):
    create_mock = AsyncMock(return_value={"record_id": "lark-new"})
    monkeypatch.setattr("src.services.membership_service.lark.create_record", create_mock)
    monkeypatch.setattr("src.services.membership_service.telegram.send", AsyncMock())

    await membership_service.activate(
        chat_id="u1", boss_chat_id="b1",
        person_type="member", name="Alice",
        source="boss_add",
    )
    create_mock.assert_awaited_once()
    fields = create_mock.await_args.args[2]
    assert fields["Tên"] == "Alice"
    assert fields["Type"] == "member"


async def test_activate_skips_lark_when_record_id_provided(setup_db, monkeypatch):
    create_mock = AsyncMock()
    monkeypatch.setattr("src.services.membership_service.lark.create_record", create_mock)
    monkeypatch.setattr("src.services.membership_service.telegram.send", AsyncMock())

    await membership_service.activate(
        chat_id="u1", boss_chat_id="b1",
        person_type="member", name="Alice",
        source="approval",
        lark_record_id="existing-rec",
    )
    create_mock.assert_not_awaited()


async def test_activate_emits_audit_log(setup_db, monkeypatch, caplog):
    monkeypatch.setattr(
        "src.services.membership_service.lark.create_record",
        AsyncMock(return_value={"record_id": "lark-1"}),
    )
    monkeypatch.setattr("src.services.membership_service.telegram.send", AsyncMock())
    with caplog.at_level("INFO"):
        await membership_service.activate(
            chat_id="u1", boss_chat_id="b1",
            person_type="member", name="Alice",
            source="boss_add",
        )
    audit_lines = [r for r in caplog.records if "membership.activate" in r.message]
    assert audit_lines
    assert "boss_add" in audit_lines[0].message
