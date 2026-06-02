import pytest

from src.channels.web.promotion import BossPromotionService
from src.channels.web.state_repo import WebUsersRepo


@pytest.mark.asyncio
async def test_promote_creates_boss_link_and_assignment(clean_db):
    users = WebUsersRepo(clean_db)
    svc = BossPromotionService(clean_db)

    web_uid = await users.create(name="Boss X", is_boss=False)
    boss_id = await svc.promote(web_uid)

    assert isinstance(boss_id, int) and boss_id > 0
    async with clean_db.acquire() as c:
        link = await c.fetchrow(
            "SELECT * FROM account_links WHERE provider='web' AND provider_user_id=$1",
            web_uid,
        )
        asg = await c.fetchrow(
            "SELECT * FROM bot_account_assignments WHERE boss_id=$1 AND provider='web'",
            boss_id,
        )
        wu = await c.fetchrow(
            "SELECT is_boss, boss_user_id FROM web_users WHERE id=$1", web_uid
        )
    assert link is not None and link["boss_id"] == boss_id
    assert asg is not None and asg["status"] == "active"
    assert wu["is_boss"] is True and wu["boss_user_id"] == boss_id


@pytest.mark.asyncio
async def test_demote_clears_link_and_assignment(clean_db):
    users = WebUsersRepo(clean_db)
    svc = BossPromotionService(clean_db)
    web_uid = await users.create(name="Boss Y", is_boss=False)
    await svc.promote(web_uid)

    await svc.demote(web_uid)
    async with clean_db.acquire() as c:
        link = await c.fetchrow(
            "SELECT * FROM account_links WHERE provider='web' AND provider_user_id=$1",
            web_uid,
        )
        wu = await c.fetchrow(
            "SELECT is_boss FROM web_users WHERE id=$1", web_uid
        )
    assert link is None
    assert wu["is_boss"] is False
