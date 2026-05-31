import asyncpg

from src.domain.bot_account import AssignmentStatus, BotAccountAssignment
from src.repositories.base import BossScopedRepo


def _row_to_assignment(r: asyncpg.Record) -> BotAccountAssignment:
    return BotAccountAssignment(
        boss_id=r["boss_id"],
        provider=r["provider"],
        bot_account_id=r["bot_account_id"],
        assignment_kind=r["assignment_kind"],
        status=AssignmentStatus(r["status"]),
        assigned_at=r["assigned_at"],
        assigned_by=r["assigned_by"],
        accepted_at=r["accepted_at"],
    )


class BotAccountAssignmentsRepo(BossScopedRepo):
    async def get(self, provider: str) -> BotAccountAssignment | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT * FROM bot_account_assignments
                WHERE boss_id=$1 AND provider=$2
                """,
                self.ctx.boss_id,
                provider,
            )
            return _row_to_assignment(row) if row else None

    async def list_for_boss(self) -> list[BotAccountAssignment]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT * FROM bot_account_assignments WHERE boss_id=$1",
                self.ctx.boss_id,
            )
            return [_row_to_assignment(r) for r in rows]

    async def list_for_account(self, bot_account_id: int) -> list[BotAccountAssignment]:
        assert self.ctx.user_role == "superadmin"
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT * FROM bot_account_assignments WHERE bot_account_id=$1",
                bot_account_id,
            )
            return [_row_to_assignment(r) for r in rows]

    async def upsert(
        self,
        boss_id: int,
        provider: str,
        bot_account_id: int,
        assignment_kind: str,
        assigned_by: int,
        status: AssignmentStatus = AssignmentStatus.PENDING_ACCEPT,
    ) -> None:
        assert self.ctx.user_role == "superadmin" or boss_id == self.ctx.boss_id
        async with self.pool.acquire() as c:
            await c.execute(
                """
                INSERT INTO bot_account_assignments (boss_id, provider, bot_account_id,
                                                     assignment_kind, status, assigned_by)
                VALUES ($1,$2,$3,$4,$5,$6)
                ON CONFLICT (boss_id, provider) DO UPDATE SET
                  bot_account_id=EXCLUDED.bot_account_id,
                  assignment_kind=EXCLUDED.assignment_kind,
                  status=EXCLUDED.status,
                  assigned_by=EXCLUDED.assigned_by,
                  assigned_at=NOW()
                """,
                boss_id,
                provider,
                bot_account_id,
                assignment_kind,
                status.value,
                assigned_by,
            )

    async def mark_accepted(self, provider: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE bot_account_assignments
                SET status='active', accepted_at=NOW()
                WHERE boss_id=$1 AND provider=$2
                """,
                self.ctx.boss_id,
                provider,
            )
