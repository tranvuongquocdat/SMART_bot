import pytest

from src.domain.bot_account import BotAccountOwnership, BotAccountStatus
from src.repositories.base import BossContext
from src.repositories.bot_accounts import BotAccountsRepo


@pytest.mark.asyncio
async def test_insert_platform_account_and_list(db_pool, boss_user):
    repo = BotAccountsRepo(db_pool, BossContext(boss_id=boss_user["id"], user_role="superadmin"))
    bid = await repo.insert(
        provider="zalo",
        provider_user_id="bot1",
        account_kind="personal",
        ownership=BotAccountOwnership.PLATFORM,
        owner_boss_id=None,
        display_name="Platform Bot 1",
    )
    fetched = await repo.get(bid)
    assert fetched is not None
    assert fetched.ownership == BotAccountOwnership.PLATFORM
    assert fetched.status == BotAccountStatus.ACTIVE
    assert fetched.owner_boss_id is None


@pytest.mark.asyncio
async def test_update_status(db_pool, boss_user):
    repo = BotAccountsRepo(db_pool, BossContext(boss_id=boss_user["id"], user_role="superadmin"))
    bid = await repo.insert(
        provider="zalo",
        provider_user_id="bot2",
        account_kind="personal",
        ownership=BotAccountOwnership.BOSS_OWNED,
        owner_boss_id=boss_user["id"],
        display_name="Boss Bot",
    )
    await repo.update_status(bid, BotAccountStatus.BANNED, reason="dispute")
    fetched = await repo.get(bid)
    assert fetched.status == BotAccountStatus.BANNED
    assert fetched.status_reason == "dispute"
