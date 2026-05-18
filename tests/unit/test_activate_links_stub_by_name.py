"""When activate() runs for a person whose name already exists as a stub
Person row (no Chat ID), it must link to that row instead of creating a
duplicate. Otherwise the stub's tasks/reminders get orphaned."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.services import membership_service


_STUB_ROW = {"record_id": "recStub", "Tên": "Tân", "Type": "member"}
# Boss row used by activate to locate Lark base + People table
_BOSS_ROW = {
    "chat_id": "boss-1",
    "name": "Boss",
    "company": "Acme",
    "lark_base_token": "base",
    "lark_table_people": "ppl",
}


@pytest_asyncio.fixture
async def in_memory_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


async def test_activate_links_existing_stub_row_by_name(in_memory_db, monkeypatch):
    monkeypatch.setattr(
        "src.services.membership_service.lark.search_records",
        AsyncMock(return_value=[_STUB_ROW]),
    )
    update_mock = AsyncMock(return_value={"record_id": "recStub"})
    create_mock = AsyncMock(return_value={"record_id": "recNEW"})
    monkeypatch.setattr(
        "src.services.membership_service.lark.update_record", update_mock,
    )
    monkeypatch.setattr(
        "src.services.membership_service.lark.create_record", create_mock,
    )
    monkeypatch.setattr(
        "src.services.membership_service.db.get_boss",
        AsyncMock(return_value=_BOSS_ROW),
    )
    monkeypatch.setattr(
        "src.services.membership_service.db.lookup_external_for_person",
        AsyncMock(return_value=None),
    )

    # Avoid the approved-user notification path
    monkeypatch.setattr(
        "src.services.membership_service.telegram.send", AsyncMock(),
    )

    await membership_service.activate(
        chat_id="zalo-uid-123",
        boss_chat_id="boss-1",
        person_type="member",
        name="Tân",
        source="link_contact",
        lark_record_id=None,
    )

    # Stub must be UPDATED, not duplicated.
    update_mock.assert_awaited()
    args = update_mock.await_args.args
    # update_record signature: (base_token, table_id, record_id, fields)
    assert args[2] == "recStub", f"expected to update recStub, got {args[2]!r}"
    assert "Chat ID" in args[3]
    create_mock.assert_not_awaited()


async def test_activate_creates_new_row_when_no_stub_match(
    in_memory_db, monkeypatch,
):
    """No name match → fall through to existing create_record path."""
    monkeypatch.setattr(
        "src.services.membership_service.lark.search_records",
        AsyncMock(return_value=[
            {"record_id": "recX", "Tên": "Khác hẳn", "Chat ID": None},
        ]),
    )
    update_mock = AsyncMock()
    create_mock = AsyncMock(return_value={"record_id": "recNEW"})
    monkeypatch.setattr(
        "src.services.membership_service.lark.update_record", update_mock,
    )
    monkeypatch.setattr(
        "src.services.membership_service.lark.create_record", create_mock,
    )
    monkeypatch.setattr(
        "src.services.membership_service.db.get_boss",
        AsyncMock(return_value=_BOSS_ROW),
    )
    monkeypatch.setattr(
        "src.services.membership_service.db.lookup_external_for_person",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "src.services.membership_service.telegram.send", AsyncMock(),
    )

    await membership_service.activate(
        chat_id="zalo-uid-456",
        boss_chat_id="boss-1",
        person_type="member",
        name="Hằng",
        source="link_contact",
        lark_record_id=None,
    )

    create_mock.assert_awaited_once()
    update_mock.assert_not_awaited()
