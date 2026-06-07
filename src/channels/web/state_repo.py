"""WebUsersRepo + WebGroupsRepo — CRUD trên 3 bảng sim của channel web.

Không phải BossScopedRepo — web channel là sim layer dùng cross-boss
trong dev/test, không cần RLS theo boss.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class WebUsersRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def create(
        self, *, name: str, is_boss: bool, boss_user_id: int | None = None
    ) -> str:
        uid = _gen_id("u")
        async with self.pool.acquire() as c:
            await c.execute(
                """
                INSERT INTO web_users (id, name, is_boss, boss_user_id)
                VALUES ($1, $2, $3, $4)
                """,
                uid, name, is_boss, boss_user_id,
            )
        return uid

    async def get(self, web_user_id: str) -> dict[str, Any] | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM web_users WHERE id=$1", web_user_id
            )
        return dict(row) if row else None

    async def list_all(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT w.*, u.role AS app_role
                FROM web_users w
                LEFT JOIN users u ON u.id = w.boss_user_id
                ORDER BY w.created_at
                """
            )
        return [dict(r) for r in rows]

    async def rename(self, web_user_id: str, new_name: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                "UPDATE web_users SET name=$2 WHERE id=$1",
                web_user_id, new_name,
            )

    async def set_boss(
        self, web_user_id: str, is_boss: bool, boss_user_id: int | None
    ) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE web_users SET is_boss=$2, boss_user_id=$3 WHERE id=$1
                """,
                web_user_id, is_boss, boss_user_id,
            )

    async def delete(self, web_user_id: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM web_users WHERE id=$1", web_user_id)


class WebGroupsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def create(self, *, name: str, member_ids: list[str]) -> str:
        gid = _gen_id("g")
        async with self.pool.acquire() as c:
            async with c.transaction():
                await c.execute(
                    "INSERT INTO web_groups (id, name) VALUES ($1, $2)",
                    gid, name,
                )
                if member_ids:
                    await c.executemany(
                        "INSERT INTO web_group_members (group_id, web_user_id) VALUES ($1, $2)",
                        [(gid, u) for u in member_ids],
                    )
        return gid

    async def get(self, group_id: str) -> dict[str, Any] | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM web_groups WHERE id=$1", group_id
            )
        return dict(row) if row else None

    async def list_all(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                "SELECT * FROM web_groups ORDER BY created_at"
            )
        return [dict(r) for r in rows]

    async def list_members(self, group_id: str) -> list[str]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT web_user_id FROM web_group_members
                WHERE group_id=$1 ORDER BY web_user_id
                """,
                group_id,
            )
        return [r["web_user_id"] for r in rows]

    async def list_for_user(self, web_user_id: str) -> list[dict[str, Any]]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT g.* FROM web_groups g
                JOIN web_group_members m ON m.group_id = g.id
                WHERE m.web_user_id = $1
                ORDER BY g.created_at
                """,
                web_user_id,
            )
        return [dict(r) for r in rows]

    async def add_member(self, group_id: str, web_user_id: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                INSERT INTO web_group_members (group_id, web_user_id)
                VALUES ($1, $2) ON CONFLICT DO NOTHING
                """,
                group_id, web_user_id,
            )

    async def remove_member(self, group_id: str, web_user_id: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                DELETE FROM web_group_members
                WHERE group_id=$1 AND web_user_id=$2
                """,
                group_id, web_user_id,
            )

    async def delete(self, group_id: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute("DELETE FROM web_groups WHERE id=$1", group_id)
