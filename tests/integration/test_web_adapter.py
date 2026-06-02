import asyncio
from types import SimpleNamespace

import pytest

from src.channels.web.adapter import WebAdapter
from src.channels.web.sse import SSEHub
from src.channels.web.state_repo import WebGroupsRepo, WebUsersRepo


@pytest.mark.asyncio
async def test_send_text_dm_broadcasts_to_single_recipient(clean_db):
    users = WebUsersRepo(clean_db)
    groups = WebGroupsRepo(clean_db)
    u1 = await users.create(name="Boss A", is_boss=True)

    hub = SSEHub()
    client = hub.attach(u1)
    adapter = WebAdapter(bus=None, sse_hub=hub, groups_repo=groups)

    bot_acc = SimpleNamespace(id=1)
    await adapter.send_text(bot_acc, f"dm:{u1}", "hello", "user")
    ev = await asyncio.wait_for(client.queue.get(), timeout=0.5)
    assert ev["kind"] == "message"
    assert ev["text"] == "hello"
    assert ev["sender_kind"] == "bot"
    assert ev["chat_id"] == f"dm:{u1}"


@pytest.mark.asyncio
async def test_send_text_group_broadcasts_to_all_members(clean_db):
    users = WebUsersRepo(clean_db)
    groups = WebGroupsRepo(clean_db)
    u1 = await users.create(name="A", is_boss=True)
    u2 = await users.create(name="B", is_boss=False)
    gid = await groups.create(name="team", member_ids=[u1, u2])

    hub = SSEHub()
    c1 = hub.attach(u1)
    c2 = hub.attach(u2)
    adapter = WebAdapter(bus=None, sse_hub=hub, groups_repo=groups)

    bot_acc = SimpleNamespace(id=1)
    await adapter.send_text(bot_acc, gid, "team msg", "group")
    e1 = await asyncio.wait_for(c1.queue.get(), 0.5)
    e2 = await asyncio.wait_for(c2.queue.get(), 0.5)
    assert e1["text"] == "team msg" and e2["text"] == "team msg"


@pytest.mark.asyncio
async def test_classify_thread_kind_and_normalize_text():
    adapter = WebAdapter(bus=None, sse_hub=SSEHub(), groups_repo=None)
    assert adapter.classify_thread_kind("dm:u-abc") == "user"
    assert adapter.classify_thread_kind("g-abc") == "group"
    # Web renders markdown — keep as-is
    assert adapter.normalize_text("**hi**") == "**hi**"
