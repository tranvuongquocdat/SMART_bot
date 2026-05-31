import asyncpg

from src.domain.boss import Boss
from src.repositories.base import BossScopedRepo


def _row_to_boss(r: asyncpg.Record) -> Boss:
    return Boss(
        id=r["id"],
        email=r["email"],
        name=r["name"],
        role=r["role"],
        tz=r["tz"],
        language=r["language"],
        smart_model_id=r["smart_model_id"],
        fast_model_id=r["fast_model_id"],
        vision_model_id=r["vision_model_id"],
        subscription_status=r["subscription_status"],
        subscription_expiry=r["subscription_expiry"],
        cost_cap_usd_daily=float(r["cost_cap_usd_daily"]),
    )


class UsersRepo(BossScopedRepo):
    async def get_me(self) -> Boss | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT * FROM users WHERE id=$1", self.ctx.boss_id)
            return _row_to_boss(row) if row else None

    async def get_by_email(self, email: str) -> Boss | None:
        # superadmin operation — bypass boss_id filter
        assert self.ctx.user_role == "superadmin", "get_by_email requires superadmin"
        async with self.pool.acquire() as c:
            row = await c.fetchrow("SELECT * FROM users WHERE email=$1", email.lower())
            return _row_to_boss(row) if row else None

    async def list_all(self) -> list[Boss]:
        assert self.ctx.user_role == "superadmin", "list_all requires superadmin"
        async with self.pool.acquire() as c:
            rows = await c.fetch("SELECT * FROM users ORDER BY id")
            return [_row_to_boss(r) for r in rows]

    async def insert(
        self,
        email: str,
        name: str | None,
        role: str = "boss",
        google_sub: str | None = None,
        password_hash: str | None = None,
    ) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO users (email, name, role, google_sub, password_hash)
                VALUES ($1,$2,$3,$4,$5) RETURNING id
                """,
                email.lower(),
                name,
                role,
                google_sub,
                password_hash,
            )

    async def update_models(
        self,
        smart_id: int | None,
        fast_id: int | None,
        vision_id: int | None,
    ) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE users SET smart_model_id=$2, fast_model_id=$3, vision_model_id=$4
                WHERE id=$1
                """,
                self.ctx.boss_id,
                smart_id,
                fast_id,
                vision_id,
            )
