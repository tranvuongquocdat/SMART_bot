"""BossPromotionService — atomic upgrade web_user → real boss.

Promote:
  1. INSERT users (role='boss', email='<web_uid>@web.test.local')
  2. INSERT account_links (provider='web', provider_user_id=<web_uid>)
  3. INSERT bot_account_assignments (boss_id, provider='web', bot_account=<web bot>)
  4. UPDATE web_users SET is_boss=true, boss_user_id=<users.id>

Demote: reverse (delete account_links + assignment, set is_boss=false).
"""

from __future__ import annotations

import asyncpg


class BossPromotionService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def promote(self, web_user_id: str, role: str = "boss") -> int:
        if role not in ("boss", "superadmin"):
            raise ValueError(f"role must be 'boss' or 'superadmin', got {role!r}")
        async with self.pool.acquire() as c:
            async with c.transaction():
                wu = await c.fetchrow(
                    "SELECT name FROM web_users WHERE id=$1", web_user_id
                )
                if wu is None:
                    raise ValueError(f"web_user not found: {web_user_id}")

                boss_id = await c.fetchval(
                    """
                    INSERT INTO users (email, name, role)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (email) DO UPDATE SET
                      name=EXCLUDED.name,
                      role=EXCLUDED.role
                    RETURNING id
                    """,
                    f"{web_user_id}@web.test.local",
                    wu["name"],
                    role,
                )

                await c.execute(
                    """
                    INSERT INTO account_links (boss_id, provider, provider_user_id)
                    VALUES ($1, 'web', $2)
                    ON CONFLICT DO NOTHING
                    """,
                    boss_id, web_user_id,
                )

                bot_acc_id = await c.fetchval(
                    """
                    SELECT id FROM bot_accounts
                    WHERE provider='web' AND status='active' LIMIT 1
                    """
                )
                if bot_acc_id is None:
                    raise RuntimeError("no active web bot_account — migration not run?")

                await c.execute(
                    """
                    INSERT INTO bot_account_assignments
                      (boss_id, provider, bot_account_id, assignment_kind, status)
                    VALUES ($1, 'web', $2, 'platform_assigned', 'active')
                    ON CONFLICT (boss_id, provider) DO UPDATE
                      SET bot_account_id=EXCLUDED.bot_account_id,
                          status='active'
                    """,
                    boss_id, bot_acc_id,
                )

                await c.execute(
                    """
                    UPDATE web_users SET is_boss=TRUE, boss_user_id=$2 WHERE id=$1
                    """,
                    web_user_id, boss_id,
                )
        return boss_id

    async def demote(self, web_user_id: str) -> None:
        async with self.pool.acquire() as c:
            async with c.transaction():
                row = await c.fetchrow(
                    "SELECT boss_user_id FROM web_users WHERE id=$1", web_user_id
                )
                boss_id = row["boss_user_id"] if row else None

                await c.execute(
                    """
                    DELETE FROM account_links
                    WHERE provider='web' AND provider_user_id=$1
                    """,
                    web_user_id,
                )
                if boss_id is not None:
                    await c.execute(
                        """
                        DELETE FROM bot_account_assignments
                        WHERE boss_id=$1 AND provider='web'
                        """,
                        boss_id,
                    )
                await c.execute(
                    "UPDATE web_users SET is_boss=FALSE WHERE id=$1",
                    web_user_id,
                )
