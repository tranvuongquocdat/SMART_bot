from dataclasses import dataclass
from datetime import datetime

import asyncpg

from src.repositories.base import BossScopedRepo


@dataclass(frozen=True, slots=True)
class LinkingToken:
    token: str
    boss_id: int
    provider: str
    bot_account_id: int
    expires_at: datetime
    created_at: datetime


def _row_to_token(r: asyncpg.Record) -> LinkingToken:
    return LinkingToken(
        token=r["token"],
        boss_id=r["boss_id"],
        provider=r["provider"],
        bot_account_id=r["bot_account_id"],
        expires_at=r["expires_at"],
        created_at=r["created_at"],
    )


class LinkingTokensRepo(BossScopedRepo):
    async def get(self, token: str) -> LinkingToken | None:
        """Cross-boss lookup — token itself is the secret."""
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT * FROM linking_tokens
                WHERE token=$1 AND expires_at > NOW()
                """,
                token,
            )
            return _row_to_token(row) if row else None

    async def list_for_boss(self) -> list[LinkingToken]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM linking_tokens
                WHERE boss_id=$1 AND expires_at > NOW()
                ORDER BY created_at DESC
                """,
                self.ctx.boss_id,
            )
            return [_row_to_token(r) for r in rows]

    async def insert(
        self,
        token: str,
        provider: str,
        bot_account_id: int,
        expires_at: datetime,
    ) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                INSERT INTO linking_tokens (token, boss_id, provider, bot_account_id, expires_at)
                VALUES ($1,$2,$3,$4,$5)
                """,
                token,
                self.ctx.boss_id,
                provider,
                bot_account_id,
                expires_at,
            )

    async def delete(self, token: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM linking_tokens WHERE token=$1", token)

    async def gc_expired(self) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                WITH d AS (DELETE FROM linking_tokens WHERE expires_at <= NOW() RETURNING 1)
                SELECT COUNT(*) FROM d
                """
            ) or 0
