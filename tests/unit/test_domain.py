import dataclasses

import pytest

from src.domain.bot_account import BotAccount, BotAccountOwnership, BotAccountStatus
from src.domain.memory import Memory, MemoryScope


def test_memory_immutable_and_enum_value():
    m = Memory(
        id=1,
        boss_id=42,
        scope=MemoryScope.SEMANTIC,
        key="preferred_name",
        content="Đạt",
    )
    assert m.scope == "semantic"
    assert m.scope == MemoryScope.SEMANTIC
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.content = "x"  # type: ignore[misc]


def test_bot_account_equality_and_slots():
    a = BotAccount(
        id=1,
        provider="zalo",
        provider_user_id="abc",
        display_name="bot1",
        account_kind="personal",
        ownership=BotAccountOwnership.PLATFORM,
        owner_boss_id=None,
        status=BotAccountStatus.ACTIVE,
        status_reason=None,
        max_assigned_bosses=5,
        msgs_received_total=0,
        msgs_sent_total=0,
        last_seen_at=None,
        notes=None,
    )
    b = BotAccount(
        id=1,
        provider="zalo",
        provider_user_id="abc",
        display_name="bot1",
        account_kind="personal",
        ownership=BotAccountOwnership.PLATFORM,
        owner_boss_id=None,
        status=BotAccountStatus.ACTIVE,
        status_reason=None,
        max_assigned_bosses=5,
        msgs_received_total=0,
        msgs_sent_total=0,
        last_seen_at=None,
        notes=None,
    )
    assert a == b
    # slots — no __dict__
    assert not hasattr(a, "__dict__")
