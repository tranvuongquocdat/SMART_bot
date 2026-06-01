"""ReminderFirer — fire a due reminder exactly once + schedule next if recurring.

Subscribed to ``reminder.due`` (Batch F's APScheduler will be the producer).
Idempotency comes from a SELECT … FOR UPDATE inside a transaction that flips
status pending→fired before the outbound send. A second concurrent fire sees
the row already non-pending and exits.
"""

from dataclasses import dataclass
from typing import Any

from src.agents.registry import operation


@dataclass
class FirerCtx:
    boss: Any
    db: Any
    bus: Any


@operation(
    name="reminder_firer",
    triggered_by=["reminder.due"],
    when=None,
    deps_type=FirerCtx,
    prompt_key="",  # no LLM
    feature="",
    memory_scopes=[],
    tools=set(),
    timeout_s=10,
    progress_mode="none",
    max_concurrency_per_bot_account=10,
)
class ReminderFirer:
    async def handle(self, event: dict, ctx: FirerCtx):
        from src.services.outbound_service import OutboundService
        from src.services.reminder_service import ReminderService

        rid = event["reminder_id"]
        async with ctx.db.acquire() as c:
            async with c.transaction():
                row = await c.fetchrow(
                    """
                    SELECT * FROM scheduled_reminders
                    WHERE id=$1 AND status='pending'
                    FOR UPDATE
                    """,
                    rid,
                )
                if row is None:
                    return  # already fired / cancelled — drop silently
                # Flip state inside the same transaction so a concurrent
                # fire racing on this row will see status!='pending' above
                # and return without resending.
                await c.execute(
                    """
                    UPDATE scheduled_reminders
                    SET status='fired', fired_at=NOW()
                    WHERE id=$1
                    """,
                    rid,
                )

        out = OutboundService(ctx.db, ctx.bus)
        try:
            await out.send(
                boss_id=ctx.boss.id,
                provider=row["provider"] or "zalo",
                chat_id=row["chat_id"],
                content=f"Nhắc anh: {row['text']}",
                trigger="scheduled",
            )
        except Exception as e:
            async with ctx.db.acquire() as c:
                await c.execute(
                    """
                    UPDATE scheduled_reminders
                    SET status='failed', last_error=$2
                    WHERE id=$1
                    """,
                    rid,
                    str(e),
                )
            return

        if row["recurring"]:
            await ReminderService(ctx.db, ctx.bus).create_next(row)
