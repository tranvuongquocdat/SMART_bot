import pytest

from src.repositories.base import BossContext
from src.repositories.users import UsersRepo


@pytest.mark.asyncio
async def test_get_me(db_pool, boss_user):
    repo = UsersRepo(db_pool, BossContext(boss_id=boss_user["id"], user_role="boss"))
    me = await repo.get_me()
    assert me is not None
    assert me.email == boss_user["email"]
    assert me.role == "boss"


@pytest.mark.asyncio
async def test_get_by_email_requires_superadmin(db_pool, boss_user):
    repo = UsersRepo(db_pool, BossContext(boss_id=boss_user["id"], user_role="boss"))
    with pytest.raises(AssertionError):
        await repo.get_by_email("boss@example.com")


@pytest.mark.asyncio
async def test_update_models(db_pool, boss_user):
    repo = UsersRepo(db_pool, BossContext(boss_id=boss_user["id"], user_role="boss"))
    async with db_pool.acquire() as c:
        smart_id = await c.fetchval(
            "SELECT id FROM models WHERE provider='openai' AND name='gpt-4o-mini'"
        )
        fast_id = await c.fetchval(
            "SELECT id FROM models WHERE provider='groq' AND name='llama-3.3-70b-versatile'"
        )
    await repo.update_models(smart_id=smart_id, fast_id=fast_id, vision_id=None)
    me = await repo.get_me()
    assert me.smart_model_id == smart_id
    assert me.fast_model_id == fast_id
    assert me.vision_model_id is None
