import pytest

from src.channels.web.state_repo import WebUsersRepo, WebGroupsRepo


@pytest.mark.asyncio
async def test_web_users_crud(clean_db):
    repo = WebUsersRepo(clean_db)
    uid = await repo.create(name="User X", is_boss=False)
    assert uid.startswith("u-") and len(uid) == 10

    listed = await repo.list_all()
    assert any(u["id"] == uid and u["name"] == "User X" for u in listed)

    await repo.rename(uid, "User Y")
    one = await repo.get(uid)
    assert one["name"] == "User Y"

    await repo.delete(uid)
    assert await repo.get(uid) is None


@pytest.mark.asyncio
async def test_web_groups_crud_and_membership(clean_db):
    users = WebUsersRepo(clean_db)
    groups = WebGroupsRepo(clean_db)

    u1 = await users.create(name="A", is_boss=False)
    u2 = await users.create(name="B", is_boss=False)
    gid = await groups.create(name="team", member_ids=[u1])

    members = await groups.list_members(gid)
    assert members == [u1]

    await groups.add_member(gid, u2)
    assert set(await groups.list_members(gid)) == {u1, u2}

    await groups.remove_member(gid, u1)
    assert await groups.list_members(gid) == [u2]

    chats = await groups.list_for_user(u2)
    assert any(g["id"] == gid for g in chats)

    await groups.delete(gid)
    assert await groups.list_for_user(u2) == []
