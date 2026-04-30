"""ZaloInboundFilter — drop noisy events before save/embed/agent.

Personal Zalo account use case: huge volume of irrelevant DMs / group
chatter. The filter only forwards events that the agent actually cares
about. db.* helpers are patched per-test (no real SQLite needed).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import src.db  # noqa: F401  — register submodule for patch("src.db.*") resolution
from src.channels.zalo_bridge.inbound_filter import ZaloInboundFilter


def _ev(**overrides) -> dict:
    base = {
        "thread_type": "dm",
        "sender_uid": "ZUID-1",
        "thread_id": "T-1",
        "text": "",
        "is_mentioned": False,
    }
    base.update(overrides)
    return base


# --- DM ----------------------------------------------------------------


async def test_dm_from_registered_boss_forwards():
    f = ZaloInboundFilter(onboard_phrase="thư ký ơi")
    with patch("src.db.lookup_person_by_external",
               new_callable=AsyncMock, return_value="P-1"), \
         patch("src.db.get_boss",
               new_callable=AsyncMock, return_value={"chat_id": "P-1"}):
        assert await f.should_forward(_ev(text="anything")) is True


async def test_dm_with_onboard_phrase_from_non_boss_forwards():
    f = ZaloInboundFilter(onboard_phrase="thư ký ơi")
    with patch("src.db.lookup_person_by_external",
               new_callable=AsyncMock, return_value=None):
        assert await f.should_forward(_ev(text="Thư ký ơi, tôi muốn đăng ký")) is True


async def test_dm_from_non_boss_without_phrase_drops():
    f = ZaloInboundFilter(onboard_phrase="thư ký ơi")
    with patch("src.db.lookup_person_by_external",
               new_callable=AsyncMock, return_value=None):
        assert await f.should_forward(_ev(text="hello")) is False


async def test_dm_from_known_person_who_is_not_boss_drops():
    """external_identity exists (we've seen them in groups) but they're
    not a boss → still drop."""
    f = ZaloInboundFilter(onboard_phrase="thư ký ơi")
    with patch("src.db.lookup_person_by_external",
               new_callable=AsyncMock, return_value="P-known"), \
         patch("src.db.get_boss",
               new_callable=AsyncMock, return_value=None):
        assert await f.should_forward(_ev(text="hello")) is False


# --- Group -------------------------------------------------------------


async def test_group_already_registered_forwards():
    f = ZaloInboundFilter(onboard_phrase="thư ký ơi")
    with patch("src.db.lookup_conversation_by_external",
               new_callable=AsyncMock, return_value="C-1"), \
         patch("src.db.get_group",
               new_callable=AsyncMock, return_value={"group_chat_id": "C-1"}):
        ev = _ev(thread_type="group", text="random chat", is_mentioned=False)
        assert await f.should_forward(ev) is True


async def test_group_unregistered_with_boss_mention_forwards():
    """So the boss can run a register-this-group command."""
    f = ZaloInboundFilter(onboard_phrase="thư ký ơi")
    with patch("src.db.lookup_conversation_by_external",
               new_callable=AsyncMock, return_value=None), \
         patch("src.db.lookup_person_by_external",
               new_callable=AsyncMock, return_value="P-boss"), \
         patch("src.db.get_boss",
               new_callable=AsyncMock, return_value={"chat_id": "P-boss"}):
        ev = _ev(thread_type="group", text="@bot đăng ký", is_mentioned=True)
        assert await f.should_forward(ev) is True


async def test_group_unregistered_with_non_boss_mention_drops():
    f = ZaloInboundFilter(onboard_phrase="thư ký ơi")
    with patch("src.db.lookup_conversation_by_external",
               new_callable=AsyncMock, return_value=None), \
         patch("src.db.lookup_person_by_external",
               new_callable=AsyncMock, return_value=None):
        ev = _ev(thread_type="group", is_mentioned=True)
        assert await f.should_forward(ev) is False


async def test_group_unregistered_without_mention_drops():
    f = ZaloInboundFilter(onboard_phrase="thư ký ơi")
    with patch("src.db.lookup_conversation_by_external",
               new_callable=AsyncMock, return_value=None):
        ev = _ev(thread_type="group", is_mentioned=False)
        assert await f.should_forward(ev) is False


# --- Edge cases --------------------------------------------------------


async def test_empty_phrase_doesnt_match_anything_for_non_boss():
    f = ZaloInboundFilter(onboard_phrase="")
    with patch("src.db.lookup_person_by_external",
               new_callable=AsyncMock, return_value=None):
        assert await f.should_forward(_ev(text="anything goes here")) is False


async def test_phrase_match_is_case_insensitive():
    f = ZaloInboundFilter(onboard_phrase="thư ký ơi")
    with patch("src.db.lookup_person_by_external",
               new_callable=AsyncMock, return_value=None):
        assert await f.should_forward(_ev(text="THƯ KÝ ƠI hello")) is True


async def test_unknown_thread_type_drops():
    f = ZaloInboundFilter(onboard_phrase="thư ký ơi")
    assert await f.should_forward(_ev(thread_type="bizarre")) is False


async def test_empty_sender_uid_drops_dm():
    f = ZaloInboundFilter(onboard_phrase="thư ký ơi")
    # No phrase → drop without even looking up.
    assert await f.should_forward(_ev(sender_uid="", text="hi")) is False
