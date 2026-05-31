import asyncpg

from src.domain.prompt import Prompt
from src.repositories.base import BossScopedRepo


def _row_to_prompt(r: asyncpg.Record) -> Prompt:
    return Prompt(
        id=r["id"],
        key=r["key"],
        version=r["version"],
        body=r["body"],
        is_active=r["is_active"],
        notes=r["notes"],
        created_at=r["created_at"],
        created_by=r["created_by"],
    )


class PromptsRepo(BossScopedRepo):
    async def get_active(self, key: str) -> Prompt | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM prompts WHERE key=$1 AND is_active=TRUE",
                key,
            )
            return _row_to_prompt(row) if row else None

    async def get(self, key: str, version: int) -> Prompt | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM prompts WHERE key=$1 AND version=$2",
                key,
                version,
            )
            return _row_to_prompt(row) if row else None

    async def list_versions(self, key: str) -> list[Prompt]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT * FROM prompts WHERE key=$1 ORDER BY version DESC",
                key,
            )
            return [_row_to_prompt(r) for r in rows]

    async def insert_version(
        self, key: str, body: str, notes: str | None = None, activate: bool = False
    ) -> int:
        assert self.ctx.user_role == "superadmin"
        async with self.pool.acquire() as c:
            async with c.transaction():
                next_v = (
                    await c.fetchval(
                        "SELECT COALESCE(MAX(version),0)+1 FROM prompts WHERE key=$1", key
                    )
                    or 1
                )
                if activate:
                    await c.execute(
                        "UPDATE prompts SET is_active=FALSE WHERE key=$1 AND is_active=TRUE",
                        key,
                    )
                return await c.fetchval(
                    """
                    INSERT INTO prompts (key, version, body, is_active, notes, created_by)
                    VALUES ($1,$2,$3,$4,$5,$6) RETURNING id
                    """,
                    key,
                    next_v,
                    body,
                    activate,
                    notes,
                    self.ctx.boss_id,
                )

    async def activate(self, key: str, version: int) -> None:
        assert self.ctx.user_role == "superadmin"
        async with self.pool.acquire() as c:
            async with c.transaction():
                await c.execute(
                    "UPDATE prompts SET is_active=FALSE WHERE key=$1 AND is_active=TRUE",
                    key,
                )
                await c.execute(
                    "UPDATE prompts SET is_active=TRUE WHERE key=$1 AND version=$2",
                    key,
                    version,
                )
