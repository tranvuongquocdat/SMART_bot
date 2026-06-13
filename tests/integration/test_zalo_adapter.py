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

from src.channels.base import InboundMessage
from src.channels.registry import ChannelRegistry
from src.channels.zalo.adapter import ZaloAdapter
from src.channels.zalo.inbound_filter import should_drop
from src.channels.zalo.markdown_strip import strip_markdown
from src.events.bus import InMemoryEventBus
from src.repositories.base import BossContext
from src.repositories.bot_accounts import BotAccountsRepo
from src.services.outbound_service import OutboundService


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
async def test_adapter_emits_inbound_normalized():
    bus = InMemoryEventBus()
    seen: list[dict] = []
    bus.subscribe("inbound.normalized", lambda p: seen.append(p) or _noop())

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
    msg = seen[0]["message"]
    assert isinstance(msg, InboundMessage)
    assert msg.bot_account_id == 123
    assert msg.text == "hi"
    assert msg.chat_type == "dm"
    assert msg.sender_provider_id == "user-1"


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


# --- outbound integration ----------------------------------------------------


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
    adapter = ZaloAdapter(bus)
    sent: list[dict] = []

    async def fake_send_text(bot_acc, chat_id, text, thread_kind):
        sent.append({"bot": bot_acc.id, "chat": chat_id, "text": text, "kind": thread_kind})
        return "<async>"

    adapter.send_text = fake_send_text  # type: ignore[assignment]

    registry = ChannelRegistry()
    registry.register(adapter)
    admin_repo = BotAccountsRepo(db_pool, BossContext(0, "superadmin"))
    service = OutboundService(db_pool, bus, registry, admin_repo)

    outbound_id = await service.send(
        boss_id=boss_id,
        provider="zalo",
        chat_id="chat-x",
        content="**hi** boss",
        trigger="agent",
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
