"""link_contact_to_person routes through activate(source='link_contact').
Conflict check: if the chat_id has a pending row in a different workspace, refuse."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.context import ChatContext
from src.services import communication_service


def _ctx(boss="b1") -> ChatContext:
    return ChatContext(
        sender_chat_id=boss, sender_name="Boss", sender_type="boss",
        boss_chat_id=boss, boss_name="Acme",
        lark_base_token="base", lark_table_people="ppl",
        lark_table_tasks="tsk", lark_table_projects="prj",
        lark_table_ideas="idea", lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id=boss, is_group=False, group_name="",
        messages_collection="m", tasks_collection="t",
    )


@pytest_asyncio.fixture
async def setup_db(monkeypatch):
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    from src.db import _init_schema
    await _init_schema(conn)
    monkeypatch.setattr(db, "_db", conn)
    monkeypatch.setattr(db, "_repos", {})
    yield conn
    await conn.close()
    monkeypatch.setattr(db, "_db", None)


def _stub_workspace_resolution(monkeypatch):
    monkeypatch.setattr(
        "src.services.communication_service.lark.search_records",
        AsyncMock(return_value=[{
            "record_id": "lark-1", "Tên": "Alice", "Type": "member",
        }]),
    )
    monkeypatch.setattr(
        "src.services.communication_service.lark.update_record", AsyncMock(),
    )
    monkeypatch.setattr(
        "src.services.communication_service.db.resolve_or_create_person",
        AsyncMock(return_value="u-internal"),
    )

    async def _resolve_workspaces(ctx, workspace_ids):
        return [{
            "lark_base_token": "base", "lark_table_people": "ppl",
            "boss_id": "b1", "workspace_name": "Acme",
        }]
    import src.services._workspace_helper as _wh
    monkeypatch.setattr(_wh, "resolve_workspaces", _resolve_workspaces)


async def test_link_contact_routes_through_activate(setup_db, monkeypatch):
    activate_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.communication_service.membership_service.activate",
        activate_mock,
    )
    _stub_workspace_resolution(monkeypatch)

    await communication_service.link_contact_to_person(
        _ctx(), chat_id="12345", lark_record_id="lark-1",
    )

    activate_mock.assert_awaited_once()
    assert activate_mock.await_args.kwargs["source"] == "link_contact"


async def test_link_contact_refuses_when_pending_elsewhere(setup_db, monkeypatch):
    """Person has a pending membership in another workspace → CONFLICT, no activate call."""
    await setup_db.execute(
        "INSERT INTO memberships (chat_id, boss_chat_id, person_type, name, status) "
        "VALUES ('u-internal', 'OTHER_BOSS', 'member', 'Alice', 'pending')"
    )
    await setup_db.commit()
    activate_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.communication_service.membership_service.activate",
        activate_mock,
    )
    _stub_workspace_resolution(monkeypatch)

    result = await communication_service.link_contact_to_person(
        _ctx(), chat_id="12345", lark_record_id="lark-1",
    )
    activate_mock.assert_not_awaited()
    assert "CONFLICT" in result or "pending" in result.lower()
