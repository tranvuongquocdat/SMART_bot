"""OutboundService — single send surface for all channels.

Before: published ``outbound.send`` as a trigger; per-channel subscriber
resolved bot_account + called adapter.send_text. That coupled the trigger
flow to channel-specific subscribers and forced every new channel to add
its own outbound module.

Now: ``send()`` is the only path. It persists the queued row, resolves
the adapter via ``ChannelRegistry``, resolves the sending bot_account via
``BotAccountsRepo``, calls ``adapter.send_text`` directly, and finally
publishes ``outbound.send`` as a post-hoc notification (with ``status``
field) so observers — metrics, audit, tests — keep working.

If ``channel_registry`` or ``admin_repo`` is missing the service falls
back to "persist and publish only" (legacy stub mode) so unit tests that
don't wire the full setup still pass.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class OutboundService:
    def __init__(
        self,
        pool,
        bus,
        channel_registry: Any | None = None,
        admin_repo: Any | None = None,
    ):
        self.pool = pool
        self.bus = bus
        self.registry = channel_registry
        self.admin_repo = admin_repo

    async def send(
        self,
        *,
        boss_id: int,
        provider: str,
        chat_id: str,
        content: str,
        trigger: str,
        reply_to_message_id: int | None = None,
        chat_type: str | None = None,
    ) -> int | None:
        outbound_id = await self._persist_queued(
            boss_id, provider, chat_id, content, trigger, reply_to_message_id
        )

        status = "queued"
        error: str | None = None

        adapter = self.registry.get(provider) if self.registry is not None else None
        bot_acc = None
        if adapter is not None and self.admin_repo is not None:
            try:
                bot_acc = await self.admin_repo.find_active_for_boss(boss_id, provider)
            except Exception as exc:
                log.exception("find_active_for_boss failed")
                error = f"resolve bot_account: {exc}"[:500]

        if adapter is None:
            # Legacy stub path: no registry wired (unit-test mode).
            status = "queued"
        elif bot_acc is None and error is None:
            status = "failed"
            error = "no active bot_account"
        elif bot_acc is None:
            status = "failed"
        else:
            text = adapter.normalize_text(content)
            # chat_type tường minh (từ message.captured) thắng heuristic độ dài.
            if chat_type is not None:
                thread_kind = "group" if chat_type == "group" else "user"
            else:
                thread_kind = adapter.classify_thread_kind(chat_id)
            try:
                await adapter.send_text(bot_acc, chat_id, text, thread_kind)
                status = "sent"
            except Exception as exc:
                log.exception(
                    "adapter.send_text failed provider=%s boss=%s", provider, boss_id
                )
                status = "failed"
                error = str(exc)[:500]

        await self._finalize(outbound_id, status, error)
        await self.bus.publish(
            "outbound.send",
            {
                "outbound_id": outbound_id,
                "boss_id": boss_id,
                "provider": provider,
                "chat_id": chat_id,
                "content": content,
                "trigger": trigger,
                "reply_to_message_id": reply_to_message_id,
                "status": status,
            },
        )
        return outbound_id

    # --- internals ----------------------------------------------------------

    async def _persist_queued(
        self,
        boss_id: int,
        provider: str,
        chat_id: str,
        content: str,
        trigger: str,
        reply_to_message_id: int | None,
    ) -> int | None:
        if self.pool is None:
            return None
        try:
            async with self.pool.acquire() as c:
                return await c.fetchval(
                    """
                    INSERT INTO outbound_messages
                      (boss_id, provider, chat_id, reply_to_message_id,
                       content, trigger, status)
                    VALUES ($1,$2,$3,$4,$5,$6,'queued')
                    RETURNING id
                    """,
                    boss_id,
                    provider,
                    chat_id,
                    reply_to_message_id,
                    content,
                    trigger,
                )
        except Exception:
            log.exception("outbound_messages insert failed")
            return None

    async def _finalize(
        self, outbound_id: int | None, status: str, error: str | None
    ) -> None:
        if outbound_id is None or self.pool is None or status == "queued":
            return
        try:
            async with self.pool.acquire() as c:
                if status == "sent":
                    await c.execute(
                        "UPDATE outbound_messages SET status='sent' WHERE id=$1",
                        outbound_id,
                    )
                else:
                    await c.execute(
                        "UPDATE outbound_messages SET status=$2, error=$3 WHERE id=$1",
                        outbound_id,
                        status,
                        error,
                    )
        except Exception:
            log.exception("outbound_messages finalize failed")
