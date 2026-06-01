"""OutboundService — MVP stub.

Today: persist to ``outbound_messages`` table and publish ``outbound.send`` so
tests + later batches (E: ChannelAdapter consumers) can observe sends without
any provider wiring.

Batch E will replace the bus publish path with an actual channel adapter call
(`ctx.channels.get(provider).send(...)`); the contract stays the same.
"""

import logging

log = logging.getLogger(__name__)


class OutboundService:
    def __init__(self, pool, bus):
        self.pool = pool
        self.bus = bus

    async def send(
        self,
        *,
        boss_id: int,
        provider: str,
        chat_id: str,
        content: str,
        trigger: str,
        reply_to_message_id: int | None = None,
    ) -> int | None:
        outbound_id: int | None = None
        if self.pool is not None:
            try:
                async with self.pool.acquire() as c:
                    outbound_id = await c.fetchval(
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
                # Persistence is best-effort at MVP; do not block agent reply.
                log.exception("outbound_messages insert failed")

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
            },
        )
        return outbound_id
