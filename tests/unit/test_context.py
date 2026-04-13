import pytest
from unittest.mock import AsyncMock, patch, MagicMock

def make_membership(boss_chat_id, person_type="member", name="Test User"):
    return {
        "chat_id": "111", "boss_chat_id": str(boss_chat_id),
        "person_type": person_type, "name": name, "status": "active"
    }

def make_boss(chat_id="222", company="Co A"):
    return {
        "chat_id": str(chat_id), "name": "Boss", "company": company,
        "lark_base_token": "tok", "lark_table_people": "t1",
        "lark_table_tasks": "t2", "lark_table_projects": "t3",
        "lark_table_ideas": "t4", "lark_table_reminders": "t5",
        "lark_table_notes": "t6"
    }

@pytest.mark.asyncio
async def test_single_workspace_resolves_directly():
    """User with single workspace gets resolved without ambiguity."""
    from src import context as ctx_mod
    with patch("src.context.db_mod.get_memberships", new_callable=AsyncMock,
               return_value=[make_membership("222")]), \
         patch("src.context.db_mod.get_boss", new_callable=AsyncMock,
               return_value=make_boss("222")), \
         patch("src.context.db_mod.get_group", new_callable=AsyncMock, return_value=None):
        ctx = await ctx_mod.resolve(chat_id=111, sender_id=111, is_group=False)
    assert ctx is not None
    assert ctx.boss_chat_id == 222
    assert ctx.sender_type == "member"

@pytest.mark.asyncio
async def test_unknown_user_returns_none():
    """User not in any workspace returns None (triggers onboarding)."""
    from src import context as ctx_mod
    with patch("src.context.db_mod.get_memberships", new_callable=AsyncMock, return_value=[]), \
         patch("src.context.db_mod.get_boss", new_callable=AsyncMock, return_value=None), \
         patch("src.context.db_mod.get_group", new_callable=AsyncMock, return_value=None):
        ctx = await ctx_mod.resolve(chat_id=999, sender_id=999, is_group=False)
    assert ctx is None

@pytest.mark.asyncio
async def test_multi_workspace_returns_all_memberships():
    """User in 2 workspaces gets both in all_memberships."""
    from src import context as ctx_mod
    memberships = [make_membership("100", "member"), make_membership("200", "partner")]
    with patch("src.context.db_mod.get_memberships", new_callable=AsyncMock,
               return_value=memberships), \
         patch("src.context.db_mod.get_boss", new_callable=AsyncMock,
               return_value=make_boss("100")), \
         patch("src.context.db_mod.get_group", new_callable=AsyncMock, return_value=None):
        ctx = await ctx_mod.resolve(chat_id=111, sender_id=111, is_group=False)
    assert ctx is not None
    assert len(ctx.all_memberships) == 2

@pytest.mark.asyncio
async def test_boss_resolves_own_workspace():
    """Boss messaging bot gets their own workspace resolved."""
    from src import context as ctx_mod
    boss = make_boss("111", "My Company")
    with patch("src.context.db_mod.get_memberships", new_callable=AsyncMock, return_value=[]), \
         patch("src.context.db_mod.get_boss", new_callable=AsyncMock, return_value=boss), \
         patch("src.context.db_mod.get_group", new_callable=AsyncMock, return_value=None):
        ctx = await ctx_mod.resolve(chat_id=111, sender_id=111, is_group=False)
    assert ctx is not None
    assert ctx.boss_chat_id == 111
    assert ctx.sender_type == "boss"

@pytest.mark.asyncio
async def test_group_message_resolves_via_group_map():
    """Group messages resolve workspace via group_map, not memberships."""
    from src import context as ctx_mod
    group = {"group_chat_id": "-100123", "boss_chat_id": "222", "group_name": "Team Alpha"}
    boss = make_boss("222")
    with patch("src.context.db_mod.get_group", new_callable=AsyncMock, return_value=group), \
         patch("src.context.db_mod.get_boss", new_callable=AsyncMock, return_value=boss), \
         patch("src.context.db_mod.get_membership", new_callable=AsyncMock,
               return_value=make_membership("222", "member")), \
         patch("src.context.db_mod.get_memberships", new_callable=AsyncMock, return_value=[]):
        ctx = await ctx_mod.resolve(chat_id=-100123, sender_id=456, is_group=True)
    assert ctx is not None
    assert ctx.boss_chat_id == 222
    assert ctx.is_group is True
    assert ctx.group_name == "Team Alpha"

@pytest.mark.asyncio
async def test_preferred_boss_id_selects_workspace():
    """preferred_boss_id parameter forces selection of specific workspace."""
    from src import context as ctx_mod
    memberships = [make_membership("100", "member"), make_membership("200", "partner")]
    with patch("src.context.db_mod.get_memberships", new_callable=AsyncMock,
               return_value=memberships), \
         patch("src.context.db_mod.get_boss", new_callable=AsyncMock,
               return_value=make_boss("200")), \
         patch("src.context.db_mod.get_group", new_callable=AsyncMock, return_value=None):
        ctx = await ctx_mod.resolve(chat_id=111, sender_id=111, is_group=False,
                                    preferred_boss_id=200)
    assert ctx is not None
    assert ctx.boss_chat_id == 200
