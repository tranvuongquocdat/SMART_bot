"""BotAccountService — lifecycle on top of ``bot_accounts`` +
``bot_account_assignments``.

Modes (per spec §3.2):
  - **platform**: pool of provisioned accounts shared across bosses.
    ``auto_assign`` picks the least-loaded with spare capacity and creates
    a ``pending_accept`` assignment row.
  - **boss_owned**: a single sếp owns the account; assignment is direct
    (also a single row, but ownership is enforced by a CHECK in schema).

Lifecycle:
  ``provisioned`` (bot_accounts.status=active, no assignment)
    → ``assigned`` (assignment.status=pending_accept)
    → ``active``   (assignment.status=active, inbound started)
    → ``suspended`` (assignment.status=revoked, OR bot_accounts.status=paused)

The web (Batch G) drives this via the methods below — no HTML/HTMX here.
"""

from __future__ import annotations

import logging
from typing import Any

from src.domain.bot_account import (
    BotAccountOwnership,
    BotAccountStatus,
)
from src.repositories.bot_accounts import _row_to_bot_account

log = logging.getLogger(__name__)


class NoCapacityError(LookupError):
    """No platform bot_account has free assignment slots."""


class InvalidOwnershipError(ValueError):
    """Operation rejected because target ownership doesn't match expectation."""


class BotAccountService:
    def __init__(self, pool, bus, adapter_map: dict[str, Any] | None = None):
        self.pool = pool
        self.bus = bus
        self.adapters = adapter_map or {}

    # ----- pick least-loaded platform account ------------------------------

    async def auto_assign(self, boss_id: int, provider: str) -> int:
        """Pick least-loaded platform bot_account, create pending_accept row.

        Returns the chosen bot_account_id. Raises NoCapacityError if no
        platform bot_account has free slots.
        """
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT ba.id, ba.max_assigned_bosses, ba.msgs_received_total,
                       COUNT(baa.boss_id) FILTER (WHERE baa.status='active') AS load
                FROM bot_accounts ba
                LEFT JOIN bot_account_assignments baa
                  ON baa.bot_account_id = ba.id
                WHERE ba.provider=$1
                  AND ba.ownership='platform'
                  AND ba.status='active'
                GROUP BY ba.id, ba.max_assigned_bosses, ba.msgs_received_total
                HAVING COUNT(baa.boss_id) FILTER (WHERE baa.status='active')
                       < ba.max_assigned_bosses
                ORDER BY load ASC, ba.msgs_received_total ASC
                LIMIT 1
                """,
                provider,
            )
            if row is None:
                raise NoCapacityError(f"no capacity for provider={provider}")
            await c.execute(
                """
                INSERT INTO bot_account_assignments
                  (boss_id, provider, bot_account_id, assignment_kind, status, assigned_by)
                VALUES ($1, $2, $3, 'platform_assigned', 'pending_accept', NULL)
                ON CONFLICT (boss_id, provider) DO UPDATE SET
                  bot_account_id = EXCLUDED.bot_account_id,
                  assignment_kind = EXCLUDED.assignment_kind,
                  status = 'pending_accept',
                  assigned_at = NOW(),
                  accepted_at = NULL
                """,
                boss_id,
                provider,
                row["id"],
            )
        await self.bus.publish(
            "bot_account.assigned",
            {
                "boss_id": boss_id,
                "provider": provider,
                "bot_account_id": row["id"],
                "kind": "platform_assigned",
            },
        )
        return row["id"]

    async def assign_boss_owned(
        self,
        boss_id: int,
        provider: str,
        bot_account_id: int,
        assigned_by: int | None = None,
    ) -> None:
        """Wire a boss-owned account to its (single) boss.

        Enforces ``ownership='boss_owned'`` and ``owner_boss_id == boss_id``.
        """
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM bot_accounts WHERE id=$1", bot_account_id
            )
            if row is None:
                raise LookupError(f"bot_account_id={bot_account_id} not found")
            if row["ownership"] != BotAccountOwnership.BOSS_OWNED.value:
                raise InvalidOwnershipError(
                    f"bot_account_id={bot_account_id} is not boss_owned"
                )
            if row["owner_boss_id"] != boss_id:
                raise InvalidOwnershipError(
                    "boss_owned account owner_boss_id does not match boss_id"
                )
            await c.execute(
                """
                INSERT INTO bot_account_assignments
                  (boss_id, provider, bot_account_id, assignment_kind, status, assigned_by)
                VALUES ($1, $2, $3, 'boss_owned', 'pending_accept', $4)
                ON CONFLICT (boss_id, provider) DO UPDATE SET
                  bot_account_id = EXCLUDED.bot_account_id,
                  assignment_kind = EXCLUDED.assignment_kind,
                  status = 'pending_accept',
                  assigned_by = EXCLUDED.assigned_by,
                  assigned_at = NOW(),
                  accepted_at = NULL
                """,
                boss_id,
                provider,
                bot_account_id,
                assigned_by,
            )
        await self.bus.publish(
            "bot_account.assigned",
            {
                "boss_id": boss_id,
                "provider": provider,
                "bot_account_id": bot_account_id,
                "kind": "boss_owned",
            },
        )

    # ----- accept / decline -----------------------------------------------

    async def accept(self, boss_id: int, provider: str) -> int | None:
        """Mark assignment active and start inbound listener (idempotent)."""
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """
                UPDATE bot_account_assignments
                   SET status='active', accepted_at=NOW()
                 WHERE boss_id=$1 AND provider=$2 AND status='pending_accept'
                 RETURNING bot_account_id
                """,
                boss_id,
                provider,
            )
            if row is None:
                return None
            bot_acc_row = await c.fetchrow(
                "SELECT * FROM bot_accounts WHERE id=$1", row["bot_account_id"]
            )
        adapter = self.adapters.get(provider)
        if adapter is not None and bot_acc_row is not None:
            try:
                await adapter.start_inbound(_row_to_bot_account(bot_acc_row))
            except Exception:
                log.exception(
                    "accept: start_inbound failed bot_acc=%s", row["bot_account_id"]
                )
        await self.bus.publish(
            "bot_account.accepted",
            {
                "boss_id": boss_id,
                "provider": provider,
                "bot_account_id": row["bot_account_id"],
            },
        )
        return row["bot_account_id"]

    async def decline(
        self,
        boss_id: int,
        provider: str,
        reason: str | None = None,
    ) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE bot_account_assignments
                   SET status='revoked', accepted_at=NULL
                 WHERE boss_id=$1 AND provider=$2 AND status='pending_accept'
                """,
                boss_id,
                provider,
            )
        await self.bus.publish(
            "bot_account.declined",
            {"boss_id": boss_id, "provider": provider, "reason": reason},
        )

    # ----- disable / switch -----------------------------------------------

    async def disable_boss_owned(
        self,
        bot_account_id: int,
        reason: str,
        by_user_id: int,
    ) -> None:
        """Pause a boss-owned account + audit log + stop bridge.

        Note: only ``boss_owned`` may be disabled this way; platform
        accounts require admin intervention via a different code path
        (Batch G admin).
        """
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM bot_accounts WHERE id=$1", bot_account_id
            )
            if row is None:
                raise LookupError(f"bot_account_id={bot_account_id} not found")
            if row["ownership"] != BotAccountOwnership.BOSS_OWNED.value:
                raise InvalidOwnershipError(
                    "only boss_owned bot_accounts can be disabled this way"
                )
            await c.execute(
                """
                UPDATE bot_accounts
                   SET status=$2, status_reason=$3, updated_at=NOW()
                 WHERE id=$1
                """,
                bot_account_id,
                BotAccountStatus.PAUSED.value,
                reason,
            )
            await c.execute(
                """
                INSERT INTO admin_audit_log
                  (actor_user_id, action, target_kind, target_id, reason, payload_json)
                VALUES ($1, 'disable_boss_owned_bot_acc', 'bot_account', $2, $3, '{}'::jsonb)
                """,
                by_user_id,
                str(bot_account_id),
                reason,
            )

        adapter = self.adapters.get(row["provider"])
        if adapter is not None:
            try:
                await adapter.stop_inbound(_row_to_bot_account(row))
            except Exception:
                log.exception(
                    "disable_boss_owned: stop_inbound failed bot_acc=%s",
                    bot_account_id,
                )
        await self.bus.publish(
            "bot_account.disabled",
            {
                "bot_account_id": bot_account_id,
                "reason": reason,
                "by_user_id": by_user_id,
            },
        )

    async def switch_mode(
        self,
        boss_id: int,
        provider: str,
        target_kind: str,
    ) -> None:
        """Revoke current assignment so the boss can begin a new flow.

        The actual re-assignment (auto_assign for ``platform_assigned`` /
        assign_boss_owned for ``boss_owned``) is driven by the web wizard
        (Batch G3). This call only frees the slot.
        """
        if target_kind not in ("platform_assigned", "boss_owned"):
            raise ValueError(f"invalid target_kind={target_kind}")
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """
                UPDATE bot_account_assignments
                   SET status='revoked'
                 WHERE boss_id=$1 AND provider=$2
                 RETURNING bot_account_id, assignment_kind
                """,
                boss_id,
                provider,
            )
        if row is None:
            return
        await self.bus.publish(
            "bot_account.mode_switch_requested",
            {
                "boss_id": boss_id,
                "provider": provider,
                "from_kind": row["assignment_kind"],
                "to_kind": target_kind,
                "previous_bot_account_id": row["bot_account_id"],
            },
        )
