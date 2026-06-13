import pytest

from src.repositories.base import BossContext
from src.repositories.group_notes import GroupNotesRepo


async def _mk_boss(pool, email):
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO users (email, name, role) VALUES ($1,$2,'boss') RETURNING id",
            email, email,
        )


@pytest.mark.asyncio
async def test_ensure_tracked_creates_then_reactivates_left(clean_db):
    boss = await _mk_boss(clean_db, "b1@x.test")
    repo = GroupNotesRepo(clean_db, BossContext(boss_id=boss, user_role="boss"))

    await repo.ensure_tracked("zalo", "g1", group_name="Team")
    assert await repo.bosses_tracking("zalo", "g1") == [boss]

    # boss rời nhóm -> mark_left -> không còn tracked
    await repo.mark_left(boss, "zalo", "g1")
    assert await repo.bosses_tracking("zalo", "g1") == []

    # boss quay lại nói -> ensure_tracked reactivate (status='left' -> active)
    await repo.ensure_tracked("zalo", "g1", group_name="Team")
    assert await repo.bosses_tracking("zalo", "g1") == [boss]


@pytest.mark.asyncio
async def test_ensure_tracked_keeps_manual_pause(clean_db):
    boss = await _mk_boss(clean_db, "b2@x.test")
    repo = GroupNotesRepo(clean_db, BossContext(boss_id=boss, user_role="boss"))
    await repo.ensure_tracked("zalo", "g2")
    # sếp tự tắt thủ công
    async with clean_db.acquire() as c:
        await c.execute(
            "UPDATE group_notes SET is_active=FALSE, status='paused' "
            "WHERE boss_id=$1 AND provider='zalo' AND chat_id='g2'",
            boss,
        )
    # boss nói lại -> KHÔNG tự reactivate (paused != left)
    await repo.ensure_tracked("zalo", "g2")
    assert await repo.bosses_tracking("zalo", "g2") == []
