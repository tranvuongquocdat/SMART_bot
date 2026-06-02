"""Task FINAL: end-to-end full flow.

Eight numbered flows wired against the real services + bus, with LLM and the
Zalo bridge stubbed out. The goal is to prove the wiring across batches
A-H holds together, not to exercise individual handlers in depth (those have
their own integration tests).

Mocks:
  * ``llm_gateway.complete`` → canned LLMResponse keyed by ``req.feature``.
  * ``ZaloAdapter.start_inbound`` / ``send_text`` → no Node subprocess; sent
    payloads are recorded so flows can assert on them.

DB + bus are real. Operations + tools register on import so calls flow
through the real ``OperationDispatcher`` + ``ToolDispatcher``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

# Importing these registers all ops + core tools.
import src.agents  # noqa: F401
import src.tools  # noqa: F401
from src.agents.dispatcher import OperationDispatcher
from src.agents.triggers import TriggerEngine
from src.channels.registry import ChannelRegistry
from src.channels.zalo import normalizer as zalo_normalizer
from src.channels.zalo.adapter import ZaloAdapter
from src.events.bus import InMemoryEventBus
from src.llm.base import LLMResponse, LLMUsage
from src.repositories.base import BossContext
from src.repositories.bot_accounts import BotAccountsRepo
from src.services.bot_account_service import BotAccountService
from src.services.linking_service import LinkingService
from src.services.outbound_service import OutboundService


# --------------------------------------------------------------------------
# Mocks
# --------------------------------------------------------------------------

class _FakeMem:
    async def recall(self, *a, **kw):
        return []

    async def write(self, *a, **kw):
        class _M:
            id = 1
        return _M()

    async def forget(self, *a, **kw):
        return None


class _FakeLLM:
    """Routes canned LLMResponses by feature. ``set_reminder`` flow uses a
    tool_call response; all others answer text."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.reply_with_tool_call: bool = False

    async def complete(self, req):
        self.calls.append(req.feature)
        usage = LLMUsage(50, 10, 0, 200, "stub-model", "stub")
        if self.reply_with_tool_call and req.feature == "dm_general":
            # First call → emit a set_reminder tool_call. Reset the flag so
            # the next call returns the final assistant text.
            self.reply_with_tool_call = False
            from src.llm.base import ToolCall

            due = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="tc-1",
                        name="set_reminder",
                        arguments={
                            "text": "nộp báo cáo Q2",
                            "due_at_iso": due,
                            "scope": "dm",
                        },
                    )
                ],
                usage=usage,
                status="ok",
            )
        if req.feature == "qa_with_search":
            content = "Em tóm tắt nhóm: 3 message gần đây."
        elif req.feature == "dm_general":
            content = "OK em hiểu, đã ghi nhận."
        elif req.feature == "note_update":
            content = "## Cần xử lý\n- E2E generated bullet"
        else:
            content = "(mock)"
        return LLMResponse(
            content=content, tool_calls=[], usage=usage, status="ok"
        )

    async def embed(self, texts, model):
        return [[0.0] * 8 for _ in texts]


class _AppState:
    """Minimal app_state surface the dispatcher + services touch."""

    def __init__(self, db_pool, bus, llm, mem):
        self.db_pool = db_pool
        self.bus = bus
        self.llm_gateway = llm
        self.memory_provider = mem
        self.qdrant = None
        self.retriever_factory = None
        self.channel_registry: ChannelRegistry | None = None
        self.admin_bot_accounts_repo = None
        self.outbound_service = None


# --------------------------------------------------------------------------
# Fixture: full wired environment (real bus, real services, mock LLM+Zalo)
# --------------------------------------------------------------------------

@pytest.fixture
async def e2e(clean_db):
    """One-shot environment: empty DB + bus + dispatcher + Zalo mock."""
    db_pool = clean_db

    bus = InMemoryEventBus()
    llm = _FakeLLM()
    state = _AppState(db_pool, bus, llm, _FakeMem())

    # Real ZaloAdapter, but with start_inbound + send_text stubbed: no
    # Node subprocess will be spawned.
    admin_ctx = BossContext(0, "superadmin")
    admin_repo = BotAccountsRepo(db_pool, admin_ctx)
    zalo = ZaloAdapter(bus, admin_repo)
    zalo.start_inbound = AsyncMock()
    sent_messages: list[dict] = []

    async def _fake_send(bot_acc, chat_id, text, thread_kind):
        sent_messages.append(
            {"chat_id": chat_id, "text": text, "thread_kind": thread_kind}
        )
        return "<ok>"
    zalo.send_text = _fake_send

    # Registry + outbound service mimic the real wiring.
    registry = ChannelRegistry()
    registry.register(zalo)
    state.channel_registry = registry
    state.admin_bot_accounts_repo = admin_repo
    state.outbound_service = OutboundService(db_pool, bus, registry, admin_repo)

    # Real dispatcher + trigger engine wired to the bus.
    OperationDispatcher(bus, state).attach_all()
    TriggerEngine(bus).attach_all()

    # Real Zalo normalizer wired to bus (handshake uses outbound_service).
    zalo_normalizer.register(bus, db_pool, state.outbound_service)

    yield {
        "db_pool": db_pool,
        "bus": bus,
        "llm": llm,
        "state": state,
        "zalo": zalo,
        "sent": sent_messages,
        "svc": BotAccountService(db_pool, bus, {"zalo": zalo}),
    }


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

async def _seed_boss_and_superadmin(pool) -> tuple[int, int]:
    """Bootstrap a fresh boss + a superadmin row. Returns (boss_id, admin_id)."""
    async with pool.acquire() as c:
        boss_id = await c.fetchval(
            """
            INSERT INTO users (email, name, role)
            VALUES ('boss-e2e@test.local', 'E2E Boss', 'boss') RETURNING id
            """
        )
        admin_id = await c.fetchval(
            """
            INSERT INTO users (email, name, role)
            VALUES ('admin-e2e@test.local', 'Admin', 'superadmin') RETURNING id
            """
        )
    return boss_id, admin_id


async def _seed_platform_bot_account(pool) -> int:
    """One platform-owned Zalo bot_account with capacity for 5 bosses."""
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO bot_accounts
              (provider, display_name, ownership, status, account_kind,
               provider_user_id, max_assigned_bosses)
            VALUES ('zalo', 'BotE2E', 'platform', 'active', 'personal',
                    'botuid-e2e', 5)
            RETURNING id
            """
        )


# --------------------------------------------------------------------------
# Flows 1-8 (one big test so order + state share is explicit)
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_flow_register_link_capture_reply_reminder(e2e):
    db_pool = e2e["db_pool"]
    bus = e2e["bus"]
    llm = e2e["llm"]
    state = e2e["state"]
    svc = e2e["svc"]
    sent_outbound: list[dict] = []

    async def _record_outbound(p):
        sent_outbound.append(p)
    bus.subscribe("outbound.send", _record_outbound)

    # --- Flow 1: Boss "register" ---------------------------------------
    # The app uses Google OAuth, not a /register endpoint — seeding a row
    # mirrors the post-OAuth state that downstream flows depend on.
    boss_id, admin_id = await _seed_boss_and_superadmin(db_pool)
    bot_acc_id = await _seed_platform_bot_account(db_pool)
    assert boss_id and bot_acc_id

    # --- Flow 2: Admin assigns + boss accepts → pending_accept → active
    chosen_id = await svc.auto_assign(boss_id, "zalo")
    assert chosen_id == bot_acc_id
    async with db_pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT status FROM bot_account_assignments WHERE boss_id=$1",
            boss_id,
        )
    assert row["status"] == "pending_accept"

    accepted = await svc.accept(boss_id, "zalo")
    assert accepted == bot_acc_id
    async with db_pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT status FROM bot_account_assignments WHERE boss_id=$1",
            boss_id,
        )
    assert row["status"] == "active"
    # accept() calls adapter.start_inbound — must have fired exactly once.
    assert state.channel_registry.get("zalo").start_inbound.await_count == 1

    # --- Flow 3: Boss links via DM /start <token> -----------------------
    linking = LinkingService(db_pool)
    token = await linking.generate(boss_id, "zalo", bot_acc_id)
    assert token

    sender_uid = "user-e2e-uid"
    # Simulate the raw inbound the Node bridge would emit.
    await bus.publish(
        "inbound.raw.zalo",
        {
            "bot_account_id": bot_acc_id,
            "own_uid": "botuid-e2e",
            "data": {
                "type": 0,  # DM
                "threadId": sender_uid,
                "uidFrom": sender_uid,
                "dName": "Boss",
                "msgId": "p-start",
                "content": f"/start {token}",
                "ts": 1700000000000,
            },
        },
    )
    await asyncio.sleep(0)

    async with db_pool.acquire() as c:
        link_row = await c.fetchrow(
            "SELECT boss_id FROM account_links WHERE provider='zalo' AND provider_user_id=$1",
            sender_uid,
        )
        token_remaining = await c.fetchval(
            "SELECT COUNT(*) FROM linking_tokens WHERE token=$1", token
        )
    assert link_row is not None and link_row["boss_id"] == boss_id
    assert token_remaining == 0
    # An ack must have been published.
    assert any(
        "kết nối" in (p.get("content") or "").lower() for p in sent_outbound
    ), sent_outbound

    # --- Flow 4: Capture group message ----------------------------------
    group_chat_id = "group-e2e-1"
    # Pre-publish a few message.captured events directly *via* the
    # normalizer to exercise message persistence.
    for i in range(5):
        await bus.publish(
            "inbound.raw.zalo",
            {
                "bot_account_id": bot_acc_id,
                "own_uid": "botuid-e2e",
                "data": {
                    "type": 1,  # group
                    "threadId": group_chat_id,
                    "uidFrom": f"member-{i}",
                    "dName": f"User{i}",
                    "msgId": f"g-{i}",
                    "content": f"hello {i}",
                    "ts": 1700000000000 + i,
                },
            },
        )
    await asyncio.sleep(0)

    async with db_pool.acquire() as c:
        msg_count = await c.fetchval(
            "SELECT COUNT(*) FROM messages WHERE boss_id=$1 AND chat_id=$2",
            boss_id,
            group_chat_id,
        )
    assert msg_count == 5

    # --- Flow 5: Tag bot in group → in_group_responder runs --------------
    sent_outbound.clear()
    await bus.publish(
        "inbound.raw.zalo",
        {
            "bot_account_id": bot_acc_id,
            "own_uid": "botuid-e2e",
            "data": {
                "type": 1,
                "threadId": group_chat_id,
                "uidFrom": "member-mention",
                "dName": "MentionUser",
                "msgId": "g-mention",
                "content": "@bot tóm tắt nhóm giúp anh nha em",
                "is_mentioned": True,
                "ts": 1700000010000,
            },
        },
    )
    # Give the loop a beat for op handler → tool dispatch → outbound.
    for _ in range(5):
        await asyncio.sleep(0)

    mention_replies = [
        p for p in sent_outbound if p.get("trigger") == "mention"
    ]
    assert mention_replies, f"no mention reply emitted; sent={sent_outbound}"
    assert "Em tóm tắt" in mention_replies[0]["content"]

    # --- Flow 6: Note update — threshold trigger fires after 30 msgs -----
    note_chat = "group-note-thresh"
    # Seed an empty group_note so NoteService can find/update it.
    async with db_pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO group_notes (boss_id, provider, chat_id, group_name, content)
            VALUES ($1,'zalo',$2,'NoteGroup','(empty)')
            """,
            boss_id, note_chat,
        )
    # Pre-seed some messages so NoteService has substrate.
    async with db_pool.acquire() as c:
        for i in range(3):
            await c.execute(
                """
                INSERT INTO messages (boss_id, provider, chat_id, chat_type,
                                      provider_msg_id, sender_name, text, media_kind, ts)
                VALUES ($1,'zalo',$2,'group',$3,'A','seed','text', NOW())
                """,
                boss_id, note_chat, f"seed-{i}",
            )

    note_fires: list[dict] = []

    async def _collect_fire(p):
        note_fires.append(p)
    bus.subscribe("op.note_updater.fire", _collect_fire)

    note_updated: list[dict] = []

    async def _collect_note(p):
        note_updated.append(p)
    bus.subscribe("note.updated", _collect_note)

    # 30 captured-message events at the trigger key (boss_id, chat_id).
    for i in range(30):
        await bus.publish(
            "message.captured",
            {
                "boss_id": boss_id,
                "provider": "zalo",
                "chat_id": note_chat,
                "chat_type": "group",
                "text": f"m{i}",
                "mentions_bot": False,
                "sender_is_boss": False,
            },
        )
    for _ in range(5):
        await asyncio.sleep(0)

    assert any(f.get("reason") == "threshold" for f in note_fires), note_fires
    assert note_updated, "note.updated never published"

    # --- Flow 7: Boss DMs the bot → dm_responder replies ------------------
    sent_outbound.clear()
    await bus.publish(
        "inbound.raw.zalo",
        {
            "bot_account_id": bot_acc_id,
            "own_uid": "botuid-e2e",
            "data": {
                "type": 0,
                "threadId": sender_uid,
                "uidFrom": sender_uid,
                "dName": "Boss",
                "msgId": "p-dm-1",
                "content": "Em ơi, hôm nay anh phải làm gì?",
                "ts": 1700000020000,
            },
        },
    )
    for _ in range(5):
        await asyncio.sleep(0)

    dm_replies = [p for p in sent_outbound if p.get("trigger") == "dm"]
    assert dm_replies, f"no DM reply; sent={sent_outbound}"
    assert "OK em hiểu" in dm_replies[0]["content"]

    # --- Flow 8: set_reminder tool fires + ReminderFirer sends ------------
    sent_outbound.clear()
    llm.reply_with_tool_call = True  # next dm_general will call set_reminder
    await bus.publish(
        "inbound.raw.zalo",
        {
            "bot_account_id": bot_acc_id,
            "own_uid": "botuid-e2e",
            "data": {
                "type": 0,
                "threadId": sender_uid,
                "uidFrom": sender_uid,
                "dName": "Boss",
                "msgId": "p-dm-2",
                "content": "Nhắc anh nộp báo cáo Q2 lúc 3pm",
                "ts": 1700000030000,
            },
        },
    )
    for _ in range(5):
        await asyncio.sleep(0)

    async with db_pool.acquire() as c:
        rem_row = await c.fetchrow(
            """
            SELECT id, status, text FROM scheduled_reminders
            WHERE boss_id=$1 ORDER BY id DESC LIMIT 1
            """,
            boss_id,
        )
    assert rem_row is not None, "set_reminder tool did not create a row"
    assert rem_row["status"] == "pending"
    rem_id = rem_row["id"]

    # Drive the scheduler-equivalent: publish reminder.due → ReminderFirer.
    sent_outbound.clear()
    await bus.publish("reminder.due", {"reminder_id": rem_id, "boss_id": boss_id})
    for _ in range(3):
        await asyncio.sleep(0)

    async with db_pool.acquire() as c:
        rem_after = await c.fetchrow(
            "SELECT status FROM scheduled_reminders WHERE id=$1", rem_id
        )
    assert rem_after["status"] == "fired"
    scheduled_sends = [p for p in sent_outbound if p["trigger"] == "scheduled"]
    assert scheduled_sends, f"ReminderFirer did not emit; sent={sent_outbound}"
    assert "nộp báo cáo" in scheduled_sends[0]["content"].lower()


# --------------------------------------------------------------------------
# Standalone HTTP flow: register → login → dashboard reachable
# Uses the real FastAPI app + lifespan via TestClient.
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_http_login_and_dashboard_reachable(clean_db, monkeypatch):
    """Validates the auth/CSRF/session stack end-to-end.

    Mirrors what the spec calls "Flow 1" but goes through real HTTP
    (no /register exists — boss is seeded then password-set, matching the
    Google-OAuth + email-fallback path in production).
    """
    from fastapi.testclient import TestClient

    from src.web.routes.auth import hash_password

    async with clean_db.acquire() as c:
        await c.execute(
            """
            INSERT INTO users (email, name, role, password_hash)
            VALUES ('http-e2e@test.local','HTTP Boss','boss',$1)
            """,
            hash_password("pw-e2e-test"),
        )

    from src import main as main_mod
    with TestClient(main_mod.app) as client:
        client.get("/login")
        csrf = client.cookies.get("smart_csrf")
        r = client.post(
            "/login",
            data={
                "email": "http-e2e@test.local",
                "password": "pw-e2e-test",
                "_csrf": csrf,
            },
            headers={"X-CSRF-Token": csrf},
            follow_redirects=False,
        )
        assert r.status_code == 303, r.text
        assert r.headers["location"] == "/app"

        dash = client.get("/app", follow_redirects=False)
        assert dash.status_code == 200, dash.text[:200]
