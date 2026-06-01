"""Zalo channel adapter — record/replay JSONL fixture against a mocked bridge.

We don't launch a real ``node bridge.js`` here. Instead we drive
``ZaloAdapter`` against a fake subprocess that emits a known JSONL event
stream, then verify:
  - ``inbound.raw.zalo`` events are published with the bot_account id
  - The normalizer subscriber reads those, inserts a ``messages`` row,
    and publishes ``message.captured`` with proper boss_id resolved
    from ``account_links``
  - ``send_text`` writes a well-formed JSON command to the bridge stdin
"""

from __future__ import annotations

import asyncio
import io
import json

import pytest

from src.channels.zalo import normalizer as zalo_normalizer
from src.channels.zalo import outbound as zalo_outbound
from src.channels.zalo.adapter import ZaloAdapter
from src.channels.zalo.inbound_filter import should_drop
from src.channels.zalo.markdown_strip import strip_markdown
from src.events.bus import InMemoryEventBus


class _FakeStdin:
    def __init__(self):
        self.buf = bytearray()

    def write(self, b: bytes) -> None:
        self.buf.extend(b)

    async def drain(self) -> None:
        return None


class _FakeStdoutStderr:
    def __init__(self, lines: list[bytes]):
        self._lines = list(lines)

    async def readline(self) -> bytes:
        if not self._lines:
            # block forever — simulating EOF only after consumer drains
            await asyncio.sleep(3600)
            return b""
        return self._lines.pop(0)


class _FakeProc:
    """Minimal stand-in for asyncio.subprocess.Process."""

    def __init__(self, stdout_lines: list[bytes], stderr_lines: list[bytes] | None = None):
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdoutStderr(stdout_lines)
        self.stderr = _FakeStdoutStderr(stderr_lines or [])
        self.returncode = None

    def send_signal(self, _sig) -> None:
        self.returncode = 0

    async def wait(self) -> int:
        return 0

    def kill(self) -> None:
        self.returncode = -9


class _BotAcc:
    """Minimal duck-typed bot_account for adapter."""

    def __init__(self, bid: int):
        self.id = bid
        self.credentials_blob_enc = None


# --- unit-ish: filter + markdown_strip ---------------------------------------


def test_inbound_filter_drops_empty():
    assert should_drop({"text": "", "media_url": None}) is True
    assert should_drop({"text": "   "}) is True
    assert should_drop({}) is True


def test_inbound_filter_keeps_text_or_media():
    assert should_drop({"text": "hi"}) is False
    assert should_drop({"text": "", "media_url": "http://x/y"}) is False


def test_markdown_strip_removes_bold_and_links():
    out = strip_markdown("**hello** [a](b)")
    assert "**" not in out
    assert "hello" in out
    assert "a (b)" in out


# --- adapter happy path: inject fake proc → reads stdout, emits events --------


@pytest.mark.asyncio
async def test_adapter_publishes_inbound_raw_zalo():
    bus = InMemoryEventBus()
    seen: list[dict] = []
    bus.subscribe("inbound.raw.zalo", lambda p: seen.append(p) or _noop())

    adapter = ZaloAdapter(bus, bot_accounts_repo=None)

    fake = _FakeProc(
        stdout_lines=[
            (json.dumps({"event": "ready", "data": {"own_id": "999"}}) + "\n").encode(),
            (
                json.dumps(
                    {
                        "event": "message",
                        "own_uid": "999",
                        "data": {
                            "type": 0,
                            "threadId": "user-1",
                            "uidFrom": "user-1",
                            "dName": "Boss",
                            "msgId": "m1",
                            "ts": 1700000000000,
                            "text": "hi",
                            "content": "hi",
                            "content_type": "text",
                            "mentions": [],
                            "is_mentioned": False,
                            "media_url": None,
                            "reply_to": None,
                        },
                    }
                )
                + "\n"
            ).encode(),
            b"",  # EOF
        ]
    )
    bot_acc = _BotAcc(123)
    adapter._procs[bot_acc.id] = fake
    adapter._pending[bot_acc.id] = {}
    adapter._req_seq[bot_acc.id] = 0
    # Start the read loop manually (skipping subprocess spawn).
    task = asyncio.create_task(adapter._read_stdout(bot_acc, fake))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(seen) == 1
    assert seen[0]["bot_account_id"] == 123
    assert seen[0]["data"]["text"] == "hi"


async def _noop():
    return None


@pytest.mark.asyncio
async def test_adapter_send_text_writes_jsonl_command():
    bus = InMemoryEventBus()
    adapter = ZaloAdapter(bus)
    bot_acc = _BotAcc(7)
    fake = _FakeProc(stdout_lines=[])
    adapter._procs[bot_acc.id] = fake
    adapter._pending[bot_acc.id] = {}
    adapter._req_seq[bot_acc.id] = 0

    await adapter.send_text(bot_acc, "chat-1", "hello", "user")
    line = bytes(fake.stdin.buf).decode().strip()
    obj = json.loads(line)
    assert obj["method"] == "send"
    assert obj["params"]["text"] == "hello"
    assert obj["params"]["thread_kind"] == "user"
    assert obj["params"]["chat_id"] == "chat-1"


@pytest.mark.asyncio
async def test_adapter_list_members_request_reply():
    bus = InMemoryEventBus()
    adapter = ZaloAdapter(bus)
    bot_acc = _BotAcc(8)
    fake = _FakeProc(stdout_lines=[])
    adapter._procs[bot_acc.id] = fake
    adapter._pending[bot_acc.id] = {}
    adapter._req_seq[bot_acc.id] = 0

    async def respond():
        await asyncio.sleep(0.01)
        # The first request id will be 1.
        adapter._handle_reply(
            bot_acc, {"id": 1, "result": {"member_ids": ["a", "b", "c"]}}
        )

    asyncio.create_task(respond())
    members = await adapter.list_members(bot_acc, "group-x", timeout_s=2.0)
    assert members == ["a", "b", "c"]


# --- normalizer integration: inbound.raw.zalo → message.captured + DB row ---


@pytest.mark.asyncio
async def test_normalizer_dm_inserts_and_publishes(db_pool, boss_user):
    bus = InMemoryEventBus()
    zalo_normalizer.register(bus, db_pool)
    boss_id = boss_user["id"]

    # Seed: bot_account, assignment, account_link
    async with db_pool.acquire() as c:
        bot_acc_id = await c.fetchval(
            """
            INSERT INTO bot_accounts
              (provider, provider_user_id, account_kind, ownership, status, display_name)
            VALUES ('zalo','platform-bot-1','personal','platform','active','PlatBot')
            RETURNING id
            """
        )
        await c.execute(
            """
            INSERT INTO bot_account_assignments
              (boss_id, provider, bot_account_id, assignment_kind, status)
            VALUES ($1, 'zalo', $2, 'platform_assigned', 'active')
            """,
            boss_id,
            bot_acc_id,
        )
        await c.execute(
            """
            INSERT INTO account_links (boss_id, provider, provider_user_id)
            VALUES ($1, 'zalo', 'sender-uid-1')
            """,
            boss_id,
        )

    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or _noop())

    await bus.publish(
        "inbound.raw.zalo",
        {
            "bot_account_id": bot_acc_id,
            "own_uid": "platform-bot-1",
            "data": {
                "type": 0,
                "threadId": "sender-uid-1",
                "uidFrom": "sender-uid-1",
                "dName": "Boss DM",
                "msgId": "msg-100",
                "ts": 1700000001000,
                "text": "hello bot",
                "content": "hello bot",
                "mentions": [],
                "is_mentioned": False,
                "content_type": "text",
                "media_url": None,
            },
        },
    )

    assert len(captured) == 1
    assert captured[0]["boss_id"] == boss_id
    assert captured[0]["chat_type"] == "dm"
    assert captured[0]["sender_is_boss"] is True
    assert captured[0]["text"] == "hello bot"

    async with db_pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT * FROM messages WHERE boss_id=$1 AND provider_msg_id='msg-100'",
            boss_id,
        )
    assert row is not None
    assert row["text"] == "hello bot"


@pytest.mark.asyncio
async def test_normalizer_unlinked_dm_dropped(db_pool, boss_user):
    bus = InMemoryEventBus()
    zalo_normalizer.register(bus, db_pool)

    async with db_pool.acquire() as c:
        bot_acc_id = await c.fetchval(
            """
            INSERT INTO bot_accounts
              (provider, provider_user_id, account_kind, ownership, status)
            VALUES ('zalo','platform-bot-2','personal','platform','active')
            RETURNING id
            """
        )

    captured: list[dict] = []
    bus.subscribe("message.captured", lambda p: captured.append(p) or _noop())

    await bus.publish(
        "inbound.raw.zalo",
        {
            "bot_account_id": bot_acc_id,
            "own_uid": "platform-bot-2",
            "data": {
                "type": 0,
                "threadId": "unknown-uid",
                "uidFrom": "unknown-uid",
                "dName": "?",
                "msgId": "msg-unknown",
                "ts": 1700000002000,
                "text": "hi",
            },
        },
    )
    assert captured == []


@pytest.mark.asyncio
async def test_outbound_subscriber_calls_adapter(db_pool, boss_user):
    bus = InMemoryEventBus()
    boss_id = boss_user["id"]

    async with db_pool.acquire() as c:
        bot_acc_id = await c.fetchval(
            """
            INSERT INTO bot_accounts
              (provider, provider_user_id, account_kind, ownership, status)
            VALUES ('zalo','platform-bot-3','personal','platform','active')
            RETURNING id
            """
        )
        await c.execute(
            """
            INSERT INTO bot_account_assignments
              (boss_id, provider, bot_account_id, assignment_kind, status)
            VALUES ($1, 'zalo', $2, 'platform_assigned', 'active')
            """,
            boss_id,
            bot_acc_id,
        )
        outbound_id = await c.fetchval(
            """
            INSERT INTO outbound_messages (boss_id, provider, chat_id, content, trigger, status)
            VALUES ($1, 'zalo', 'chat-x', 'msg', 'agent', 'queued') RETURNING id
            """,
            boss_id,
        )

    adapter = ZaloAdapter(bus)
    sent: list[dict] = []

    async def fake_send_text(bot_acc, chat_id, text, thread_kind):
        sent.append({"bot": bot_acc.id, "chat": chat_id, "text": text, "kind": thread_kind})
        return "<async>"

    adapter.send_text = fake_send_text  # type: ignore[assignment]
    zalo_outbound.register(bus, adapter, db_pool)

    await bus.publish(
        "outbound.send",
        {
            "outbound_id": outbound_id,
            "boss_id": boss_id,
            "provider": "zalo",
            "chat_id": "chat-x",
            "content": "**hi** boss",
            "trigger": "agent",
            "reply_to_message_id": None,
        },
    )

    assert len(sent) == 1
    assert sent[0]["bot"] == bot_acc_id
    # Markdown should be stripped on outbound.
    assert "**" not in sent[0]["text"]
    assert "hi boss" in sent[0]["text"]

    async with db_pool.acquire() as c:
        status = await c.fetchval(
            "SELECT status FROM outbound_messages WHERE id=$1", outbound_id
        )
    assert status == "sent"
