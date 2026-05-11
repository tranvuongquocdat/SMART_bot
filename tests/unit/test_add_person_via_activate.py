"""people_service.add_person routes the membership write through activate(source='boss_add')."""
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

import src.db as db
from src.context import ChatContext
from src.services import people_service


def _ctx() -> ChatContext:
    return ChatContext(
        sender_chat_id="b1", sender_name="Boss", sender_type="boss",
        boss_chat_id="b1", boss_name="Acme",
        lark_base_token="base", lark_table_people="ppl",
        lark_table_tasks="tsk", lark_table_projects="prj",
        lark_table_ideas="idea", lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id="b1", is_group=False, group_name="",
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


async def test_add_person_routes_through_activate(setup_db, monkeypatch):
    monkeypatch.setattr(
        "src.services.people_service.lark.create_record",
        AsyncMock(return_value={"record_id": "rec-1"}),
    )
    activate_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.people_service.membership_service.activate", activate_mock,
    )
    monkeypatch.setattr(
        "src.services.people_service.db.resolve_or_create_person",
        AsyncMock(return_value="u1-internal"),
    )

    await people_service.add_people(
        _ctx(), name="Alice", chat_id="u1", person_type="member",
    )

    activate_mock.assert_awaited_once()
    assert activate_mock.await_args.kwargs["source"] == "boss_add"


async def test_add_person_without_chat_id_skips_activate(setup_db, monkeypatch):
    """If no chat_id supplied, only Lark write happens — no membership write."""
    monkeypatch.setattr(
        "src.services.people_service.lark.create_record",
        AsyncMock(return_value={"record_id": "rec-1"}),
    )
    activate_mock = AsyncMock()
    monkeypatch.setattr(
        "src.services.people_service.membership_service.activate", activate_mock,
    )
    await people_service.add_people(
        _ctx(), name="External Partner", person_type="partner",
    )
    activate_mock.assert_not_awaited()
