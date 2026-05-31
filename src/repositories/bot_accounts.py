import asyncpg

from src.domain.bot_account import BotAccount, BotAccountOwnership, BotAccountStatus
from src.repositories.base import BossScopedRepo


def _row_to_bot_account(r: asyncpg.Record) -> BotAccount:
    return BotAccount(
        id=r["id"],
        provider=r["provider"],
        provider_user_id=r["provider_user_id"],
        display_name=r["display_name"],
        account_kind=r["account_kind"],
        ownership=BotAccountOwnership(r["ownership"]),
        owner_boss_id=r["owner_boss_id"],
        status=BotAccountStatus(r["status"]),
        status_reason=r["status_reason"],
        max_assigned_bosses=r["max_assigned_bosses"],
        msgs_received_total=r["msgs_received_total"],
        msgs_sent_total=r["msgs_sent_total"],
        last_seen_at=r["last_seen_at"],
        notes=r["notes"],
    )


class BotAccountsRepo(BossScopedRepo):
    async def get(self, bot_account_id: int) -> BotAccount | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT * FROM bot_accounts WHERE id=$1", bot_account_id)
            return _row_to_bot_account(row) if row else None

    async def list_for_boss(self) -> list[BotAccount]:
        """List boss-owned accounts plus accounts assigned to this boss."""
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT DISTINCT ba.* FROM bot_accounts ba
                LEFT JOIN bot_account_assignments asn ON asn.bot_account_id=ba.id
                WHERE ba.owner_boss_id=$1 OR asn.boss_id=$1
                ORDER BY ba.id
                """,
                self.ctx.boss_id,
            )
            return [_row_to_bot_account(r) for r in rows]

    async def list_all(self) -> list[BotAccount]:
        assert self.ctx.user_role == "superadmin", "list_all requires superadmin"
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT * FROM bot_accounts ORDER BY id")
            return [_row_to_bot_account(r) for r in rows]

    async def insert(
        self,
        provider: str,
        provider_user_id: str,
        account_kind: str,
        ownership: BotAccountOwnership,
        owner_boss_id: int | None,
        display_name: str | None,
        credentials_blob_enc: bytes | None = None,
    ) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO bot_accounts (provider, provider_user_id, display_name,
                                          account_kind, ownership, owner_boss_id,
                                          credentials_blob_enc)
                VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id
                """,
                provider,
                provider_user_id,
                display_name,
                account_kind,
                ownership.value,
                owner_boss_id,
                credentials_blob_enc,
            )

    async def update_status(
        self,
        bot_account_id: int,
        status: BotAccountStatus,
        reason: str | None = None,
    ) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE bot_accounts SET status=$2, status_reason=$3, updated_at=NOW()
                WHERE id=$1
                """,
                bot_account_id,
                status.value,
                reason,
            )
