import pytest

from src.repositories.base import BossContext
from src.repositories.group_notes import GroupNotesRepo
from src.scheduler.jobs.group_membership_reverify import reverify_once


class _Adapter:
    provider = "zalo"

    def __init__(self, members):
        self._m = members

    async def list_members(self, bot_acc, group_id):
        return self._m


class _Reg:
    def __init__(self, a):
        self._a = a

    def adapters(self):
        return [self._a]

    def get(self, p):
        return self._a


async def _setup(pool):
    async with pool.acquire() as c:
        boss = await c.fetchval(
            "INSERT INTO users (email,name,role) VALUES ('rv@x.test','rv','boss') RETURNING id")
        acc = await c.fetchval(
            "INSERT INTO bot_accounts (provider,provider_user_id,account_kind,ownership,owner_boss_id)"
            " VALUES ('zalo','b-rv','personal','boss_owned',$1) RETURNING id", boss)
        await c.execute(
            "INSERT INTO account_links (boss_id,provider,provider_user_id) VALUES ($1,'zalo','U_BOSS')", boss)
        await c.execute(
            "INSERT INTO bot_account_assignments (boss_id,provider,bot_account_id,assignment_kind,status)"
            " VALUES ($1,'zalo',$2,'boss_owned','active')", boss, acc)
    repo = GroupNotesRepo(pool, BossContext(boss_id=boss, user_role="boss"))
    await repo.ensure_tracked("zalo", "gx")
    return boss, acc, repo


@pytest.mark.asyncio
async def test_reverify_deactivates_when_boss_absent(clean_db):
    boss, acc, repo = await _setup(clean_db)
    await reverify_once(clean_db, _Reg(_Adapter(["U_OTHER"])))  # boss KHÔNG còn
    assert await repo.bosses_tracking("zalo", "gx") == []


@pytest.mark.asyncio
async def test_reverify_keeps_when_boss_present(clean_db):
    boss, acc, repo = await _setup(clean_db)
    await reverify_once(clean_db, _Reg(_Adapter(["U_BOSS", "U_OTHER"])))
    assert await repo.bosses_tracking("zalo", "gx") == [boss]
