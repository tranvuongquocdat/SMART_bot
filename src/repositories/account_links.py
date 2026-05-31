from dataclasses import dataclass
from datetime import datetime

import asyncpg

from src.repositories.base import BossScopedRepo


@dataclass(frozen=True, slots=True)
class AccountLink:
    boss_id: int
    provider: str
    provider_user_id: str
    linked_at: datetime


def _row_to_link(r: asyncpg.Record) -> AccountLink:
    return AccountLink(
        boss_id=r["boss_id"],
        provider=r["provider"],
        provider_user_id=r["provider_user_id"],
        linked_at=r["linked_at"],
    )


class AccountLinksRepo(BossScopedRepo):
    async def list_for_boss(self) -> list[AccountLink]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT * FROM account_links WHERE boss_id=$1 ORDER BY linked_at DESC",
                self.ctx.boss_id,
            )
            return [_row_to_link(r) for r in rows]

    async def lookup(self, provider: str, provider_user_id: str) -> AccountLink | None:
        """Cross-boss lookup (used by message router)."""
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT * FROM account_links
                WHERE provider=$1 AND provider_user_id=$2
                """,
                provider,
                provider_user_id,
            )
            return _row_to_link(row) if row else None

    async def insert(self, provider: str, provider_user_id: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                INSERT INTO account_links (boss_id, provider, provider_user_id)
                VALUES ($1,$2,$3)
                ON CONFLICT (provider, provider_user_id) DO UPDATE SET
                  boss_id=EXCLUDED.boss_id, linked_at=NOW()
                """,
                self.ctx.boss_id,
                provider,
                provider_user_id,
            )

    async def delete(self, provider: str, provider_user_id: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                DELETE FROM account_links
                WHERE boss_id=$1 AND provider=$2 AND provider_user_id=$3
                """,
                self.ctx.boss_id,
                provider,
                provider_user_id,
            )
