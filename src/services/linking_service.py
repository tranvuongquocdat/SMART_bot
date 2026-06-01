"""LinkingService — short-lived tokens for boss<->Zalo account handshake.

Flow (Zalo example):
  1. Web (Batch G) calls ``generate(boss_id, provider, bot_account_id)`` to
     get a token. Web shows ``/start <token>`` to the boss.
  2. Boss DMs the bot_account on Zalo with the literal message
     ``/start <token>``.
  3. The Zalo normalizer (``src/channels/zalo/normalizer.py``) intercepts
     the message and calls ``consume(token, sender_uid, bot_account_id)``.
  4. On valid token: insert ``account_links`` row + delete token + return
     ``boss_id``. The normalizer then emits an outbound ack.

Tokens are 16-byte url-safe secrets with a 10-minute TTL. Used-once: the
``consume`` call deletes the row whether it was a valid match or not (to
prevent retry once the bot has acknowledged).
"""

from __future__ import annotations

import logging
import secrets

log = logging.getLogger(__name__)


class LinkingService:
    TOKEN_TTL_MINUTES = 10

    def __init__(self, pool):
        self.pool = pool

    async def generate(
        self,
        boss_id: int,
        provider: str,
        bot_account_id: int,
    ) -> str:
        """Mint a fresh token. Returns the token string to display to the boss."""
        token = secrets.token_urlsafe(16)
        async with self.pool.acquire() as c:
            await c.execute(
                f"""
                INSERT INTO linking_tokens
                  (token, boss_id, provider, bot_account_id, expires_at)
                VALUES ($1, $2, $3, $4,
                        NOW() + INTERVAL '{self.TOKEN_TTL_MINUTES} minutes')
                """,
                token,
                boss_id,
                provider,
                bot_account_id,
            )
        return token

    async def consume(
        self,
        token: str,
        sender_provider_uid: str,
        bot_account_id: int,
    ) -> int | None:
        """Validate token + insert link. Returns boss_id on success, else None.

        Constraints checked:
          - token exists and is not expired
          - token was issued for THIS bot_account_id (anti-replay across acc)
        """
        async with self.pool.acquire() as c:
            async with c.transaction():
                row = await c.fetchrow(
                    """
                    SELECT token, boss_id, provider, bot_account_id, expires_at
                      FROM linking_tokens
                     WHERE token=$1
                       AND expires_at > NOW()
                     FOR UPDATE
                    """,
                    token,
                )
                if row is None:
                    log.info("linking token not found or expired token=%s...", token[:6])
                    return None
                if row["bot_account_id"] != bot_account_id:
                    log.info(
                        "linking token bot_account mismatch expected=%s got=%s",
                        row["bot_account_id"],
                        bot_account_id,
                    )
                    return None

                await c.execute(
                    """
                    INSERT INTO account_links (boss_id, provider, provider_user_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (provider, provider_user_id) DO UPDATE SET
                      boss_id = EXCLUDED.boss_id,
                      linked_at = NOW()
                    """,
                    row["boss_id"],
                    row["provider"],
                    sender_provider_uid,
                )
                await c.execute(
                    "DELETE FROM linking_tokens WHERE token=$1", token
                )
        return row["boss_id"]

    async def revoke(self, token: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM linking_tokens WHERE token=$1", token)

    async def gc_expired(self) -> int:
        async with self.pool.acquire() as c:
            n = await c.fetchval(
                """
                WITH d AS (
                  DELETE FROM linking_tokens WHERE expires_at <= NOW()
                  RETURNING 1
                )
                SELECT COUNT(*) FROM d
                """
            )
        return int(n or 0)
