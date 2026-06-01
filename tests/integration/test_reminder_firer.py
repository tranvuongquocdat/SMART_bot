"""ReminderFirer integration: fire-once + recurring next-occurrence."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import src.agents  # noqa: F401 — register all ops
from src.agents.dispatcher import OperationDispatcher
from src.events.bus import InMemoryEventBus


class _State:
    def __init__(self, db_pool, bus):
        self.db_pool = db_pool
        self.bus = bus
        self.llm_gateway = None
        self.memory_provider = None
        self.qdrant = None
        self.retriever_factory = None


async def _insert_reminder(
    pool,
    boss_id: int,
    *,
    text: str = "test",
    recurring: str | None = None,
    scope: str = "dm",
    provider: str = "zalo",
    chat_id: str = "boss-dm",
) -> int:
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO scheduled_reminders
              (boss_id, text, due_at, scope, provider, chat_id, recurring,
               created_by_op, status)
            VALUES ($1,$2,$3,$4,$5,$6,$7,'test','pending')
            RETURNING id
            """,
            boss_id,
            text,
            datetime.now(tz=timezone.utc) - timedelta(seconds=1),
            scope,
            provider,
            chat_id,
            recurring,
        )


@pytest.mark.asyncio
async def test_reminder_firer_sends_and_marks_fired(db_pool, boss_user):
    rid = await _insert_reminder(db_pool, boss_user["id"], text="Nộp báo cáo")
    bus = InMemoryEventBus()
    state = _State(db_pool, bus)
    OperationDispatcher(bus, state).attach_all()

    sent: list[dict] = []

    async def collect(p):
        sent.append(p)

    bus.subscribe("outbound.send", collect)

    await bus.publish(
        "reminder.due", {"reminder_id": rid, "boss_id": boss_user["id"]}
    )
    await asyncio.sleep(0)

    # Exactly one send
    assert len(sent) == 1
    assert "Nộp báo cáo" in sent[0]["content"]
    assert sent[0]["trigger"] == "scheduled"

    # DB state flipped to fired
    async with db_pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT status FROM scheduled_reminders WHERE id=$1", rid
        )
    assert row["status"] == "fired"


@pytest.mark.asyncio
async def test_reminder_firer_idempotent(db_pool, boss_user):
    """Two concurrent reminder.due events must result in exactly one send."""
    rid = await _insert_reminder(db_pool, boss_user["id"], text="One time")
    bus = InMemoryEventBus()
    state = _State(db_pool, bus)
    OperationDispatcher(bus, state).attach_all()

    sent: list[dict] = []

    async def collect(p):
        sent.append(p)

    bus.subscribe("outbound.send", collect)

    await asyncio.gather(
        bus.publish("reminder.due", {"reminder_id": rid, "boss_id": boss_user["id"]}),
        bus.publish("reminder.due", {"reminder_id": rid, "boss_id": boss_user["id"]}),
    )
    await asyncio.sleep(0)

    # Only one send was emitted (second fire saw status='fired' and exited).
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_reminder_firer_recurring_schedules_next(db_pool, boss_user):
    rid = await _insert_reminder(
        db_pool, boss_user["id"], text="Daily standup", recurring="daily"
    )
    bus = InMemoryEventBus()
    state = _State(db_pool, bus)
    OperationDispatcher(bus, state).attach_all()
    bus.subscribe("outbound.send", lambda p: asyncio.sleep(0))

    await bus.publish(
        "reminder.due", {"reminder_id": rid, "boss_id": boss_user["id"]}
    )
    await asyncio.sleep(0)

    async with db_pool.acquire() as c:
        # The first one is fired; a fresh 'pending' with same text exists.
        rows = await c.fetch(
            """
            SELECT id, status FROM scheduled_reminders
            WHERE boss_id=$1 AND text='Daily standup' ORDER BY id
            """,
            boss_user["id"],
        )
    statuses = [r["status"] for r in rows]
    assert "fired" in statuses
    assert "pending" in statuses
    assert len(rows) == 2
