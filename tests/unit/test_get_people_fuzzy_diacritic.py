"""Fuzzy match in get_person must be diacritic- and case-insensitive so a
typo like 'Tan' still surfaces the canonical row 'Tân Nguyễn', avoiding
duplicate stubs."""
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
        boss_chat_id="b1", boss_name="Boss",
        lark_base_token="base", lark_table_people="ppl",
        lark_table_tasks="tsk", lark_table_projects="prj",
        lark_table_ideas="idea", lark_table_reminders="rmd",
        lark_table_notes="notes",
        chat_id="b1", is_group=False, group_name="",
        messages_collection="m", tasks_collection="t",
    )


_PEOPLE_ROWS = [
    {"record_id": "recA", "Tên": "Tân Nguyễn", "Type": "member", "Nhóm": "Design"},
    {"record_id": "recB", "Tên": "Minh Lê",   "Type": "member", "Nhóm": "Sale"},
]


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


@pytest.mark.parametrize("query", ["tan", "Tan", "TÂN", " tân ", "tÂn"])
async def test_get_person_matches_across_diacritics_case_whitespace(
    query, in_memory_db, monkeypatch,
):
    monkeypatch.setattr(
        "src.services.people_service.lark.search_records",
        AsyncMock(return_value=_PEOPLE_ROWS),
    )
    # identity.resolve_candidates is called for connection state; make it inert
    monkeypatch.setattr(
        "src.identity.resolve_candidates",
        AsyncMock(return_value=[]),
    )

    result = await people_service.get_person(_ctx(), name=query)

    assert "Tân Nguyễn" in result, f"failed for query={query!r}: {result}"
