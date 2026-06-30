import pytest

from src.repositories.base import BossContext
from src.repositories.group_notes import GroupNotesRepo


@pytest.mark.asyncio
async def test_insert_and_get_by_chat(db_pool, boss_user):
    repo = GroupNotesRepo(db_pool, BossContext(boss_id=boss_user["id"], user_role="boss"))
    nid = await repo.insert(provider="zalo", chat_id="g1", group_name="Sales Team")
    fetched = await repo.get_by_chat("zalo", "g1")
    assert fetched is not None
    assert fetched.id == nid
    assert fetched.group_name == "Sales Team"
    assert fetched.content == ""


@pytest.mark.asyncio
async def test_update_content_writes_version(db_pool, boss_user):
    repo = GroupNotesRepo(db_pool, BossContext(boss_id=boss_user["id"], user_role="boss"))
    nid = await repo.insert(provider="zalo", chat_id="g1", group_name="Sales Team")
    await repo.update_content(nid, "## Cần sếp xử lý\n- task A", emitted_by="note_updater")
    fetched = await repo.get(nid)
    assert "task A" in fetched.content

    async with db_pool.acquire() as c:
        versions = await c.fetch(
            "SELECT * FROM group_note_versions WHERE group_note_id=$1", nid
        )
        assert len(versions) == 1
        assert versions[0]["emitted_by"] == "note_updater"


@pytest.mark.asyncio
async def test_boss_scope_isolation(db_pool, boss_user):
    """A second boss must not see boss_user's notes."""
    repo = GroupNotesRepo(db_pool, BossContext(boss_id=boss_user["id"], user_role="boss"))
    await repo.insert(provider="zalo", chat_id="g1", group_name="Sales Team")

    async with db_pool.acquire() as c:
        other_id = await c.fetchval(
            "INSERT INTO users (email,name,role) VALUES ('boss2@example.com','B2','boss') RETURNING id"
        )
    other_repo = GroupNotesRepo(db_pool, BossContext(boss_id=other_id, user_role="boss"))
    assert await other_repo.get_by_chat("zalo", "g1") is None
    assert await other_repo.list_all() == []
