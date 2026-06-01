"""Subscribe to ``outbound.send`` → resolve bot_account → adapter.send_text.

Schema of payload (published by OutboundService):
    {
      outbound_id, boss_id, provider, chat_id,
      content, trigger, reply_to_message_id
    }

We only handle ``provider == "zalo"`` and we resolve which platform/boss
bot_account to send from via the active assignment row.
"""

from __future__ import annotations

import logging

from src.channels.zalo.adapter import ZaloAdapter
from src.channels.zalo.markdown_strip import strip_markdown
from src.repositories.bot_accounts import _row_to_bot_account

log = logging.getLogger(__name__)


def _classify_thread_kind(chat_id: str) -> str:
    # Zalo group ids are typically much longer than user ids; user ids are
    # ~18 digits, group ids are 19+ digits. Heuristic kept conservative —
    # caller can pass an explicit override later.
    if not chat_id:
        return "user"
    if "@g" in chat_id:
        return "group"
    return "group" if len(chat_id) >= 19 else "user"


def register(bus, adapter: ZaloAdapter, pool, bot_accounts_repo=None) -> None:
    async def handle(payload: dict) -> None:
        if payload.get("provider") != "zalo":
            return
        boss_id = payload["boss_id"]
        chat_id = str(payload["chat_id"])
        content = strip_markdown(str(payload.get("content") or ""))
        trigger = payload.get("trigger") or "agent"
        outbound_id = payload.get("outbound_id")

        async with pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT ba.* FROM bot_accounts ba
                JOIN bot_account_assignments baa ON baa.bot_account_id = ba.id
                WHERE baa.boss_id=$1
                  AND baa.provider='zalo'
                  AND baa.status='active'
                  AND ba.status='active'
                LIMIT 1
                """,
                boss_id,
            )
        if row is None:
            log.warning(
                "outbound.send no active zalo bot_account for boss_id=%s",
                boss_id,
            )
            if outbound_id is not None:
                async with pool.acquire() as c:
                    await c.execute(
                        "UPDATE outbound_messages SET status='failed', error=$2 WHERE id=$1",
                        outbound_id,
                        "no active bot_account",
                    )
            return

        bot_acc = _row_to_bot_account(row)
        thread_kind = _classify_thread_kind(chat_id)
        try:
            await adapter.send_text(bot_acc, chat_id, content, thread_kind)
        except Exception as exc:
            log.exception("zalo send_text failed")
            if outbound_id is not None:
                async with pool.acquire() as c:
                    await c.execute(
                        "UPDATE outbound_messages SET status='failed', error=$2 WHERE id=$1",
                        outbound_id,
                        str(exc)[:500],
                    )
            return

        async with pool.acquire() as c:
            if outbound_id is not None:
                await c.execute(
                    "UPDATE outbound_messages SET status='sent' WHERE id=$1",
                    outbound_id,
                )
            else:
                await c.execute(
                    """
                    INSERT INTO outbound_messages
                      (boss_id, provider, chat_id, content, trigger, status)
                    VALUES ($1,'zalo',$2,$3,$4,'sent')
                    """,
                    boss_id,
                    chat_id,
                    content,
                    trigger,
                )

    bus.subscribe("outbound.send", handle)
