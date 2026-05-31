import json

import asyncpg

from src.domain.memory import Memory, MemoryScope
from src.repositories.base import BossScopedRepo


def _row_to_memory(r: asyncpg.Record) -> Memory:
    meta = r["meta_json"]
    if isinstance(meta, str):
        meta = json.loads(meta)
    return Memory(
        id=r["id"],
        boss_id=r["boss_id"],
        scope=MemoryScope(r["scope"]),
        key=r["key"],
        content=r["content"],
        meta=meta or {},
        qdrant_point_id=r["qdrant_point_id"],
        source=r["source"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


class MemoryEntriesRepo(BossScopedRepo):
    async def get(self, scope: MemoryScope, key: str) -> Memory | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT * FROM memory_entries
                WHERE boss_id=$1 AND scope=$2 AND key=$3
                """,
                self.ctx.boss_id,
                scope.value,
                key,
            )
            return _row_to_memory(row) if row else None

    async def get_by_id(self, memory_id: int) -> Memory | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM memory_entries WHERE id=$1 AND boss_id=$2",
                memory_id,
                self.ctx.boss_id,
            )
            return _row_to_memory(row) if row else None

    async def list_by_scope(
        self, scope: MemoryScope, limit: int = 100
    ) -> list[Memory]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM memory_entries
                WHERE boss_id=$1 AND scope=$2
                ORDER BY updated_at DESC LIMIT $3
                """,
                self.ctx.boss_id,
                scope.value,
                limit,
            )
            return [_row_to_memory(r) for r in rows]

    async def list_by_ids(self, ids: "list[int]") -> list[Memory]:
        if not ids:
            return []
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM memory_entries
                WHERE id = ANY($1::BIGINT[]) AND boss_id=$2
                """,
                ids,
                self.ctx.boss_id,
            )
        by_id = {r["id"]: _row_to_memory(r) for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    async def update_content(self, memory_id: int, content: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE memory_entries
                SET content=$3, updated_at=NOW()
                WHERE id=$1 AND boss_id=$2
                """,
                memory_id,
                self.ctx.boss_id,
                content,
            )

    async def set_qdrant_point(self, memory_id: int, qdrant_point_id: str) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE memory_entries
                SET qdrant_point_id=$3, updated_at=NOW()
                WHERE id=$1 AND boss_id=$2
                """,
                memory_id,
                self.ctx.boss_id,
                qdrant_point_id,
            )

    async def list(self, scope: MemoryScope, limit: int = 100) -> list[Memory]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM memory_entries
                WHERE boss_id=$1 AND scope=$2
                ORDER BY updated_at DESC LIMIT $3
                """,
                self.ctx.boss_id,
                scope.value,
                limit,
            )
            return [_row_to_memory(r) for r in rows]

    async def upsert(
        self,
        scope: MemoryScope,
        key: str | None,
        content: str,
        meta: dict | None = None,
        qdrant_point_id: str | None = None,
        source: str = "agent_tool",
    ) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO memory_entries (boss_id, scope, key, content, meta_json,
                                            qdrant_point_id, source)
                VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7)
                ON CONFLICT (boss_id, scope, key) DO UPDATE SET
                  content=EXCLUDED.content, meta_json=EXCLUDED.meta_json,
                  qdrant_point_id=EXCLUDED.qdrant_point_id, source=EXCLUDED.source,
                  updated_at=NOW()
                RETURNING id
                """,
                self.ctx.boss_id,
                scope.value,
                key,
                content,
                json.dumps(meta or {}),
                qdrant_point_id,
                source,
            )

    async def insert(
        self,
        scope: MemoryScope,
        content: str,
        meta: dict | None = None,
        qdrant_point_id: str | None = None,
        source: str = "agent_tool",
    ) -> int:
        """Insert without key (for episodic entries — multiple allowed per scope)."""
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO memory_entries (boss_id, scope, key, content, meta_json,
                                            qdrant_point_id, source)
                VALUES ($1,$2,NULL,$3,$4::jsonb,$5,$6) RETURNING id
                """,
                self.ctx.boss_id,
                scope.value,
                content,
                json.dumps(meta or {}),
                qdrant_point_id,
                source,
            )

    async def delete(self, memory_id: int) -> None:
        async with self.pool.acquire() as c:
            await c.execute(
                "DELETE FROM memory_entries WHERE id=$1 AND boss_id=$2",
                memory_id,
                self.ctx.boss_id,
            )
