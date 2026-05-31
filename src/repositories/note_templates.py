import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from src.repositories.base import BossScopedRepo


@dataclass(frozen=True, slots=True)
class NoteTemplate:
    id: int
    name: str
    description: str | None
    is_system: bool
    owner_boss_id: int | None
    sections_json: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


def _row_to_template(r: asyncpg.Record) -> NoteTemplate:
    sections = r["sections_json"]
    if isinstance(sections, str):
        sections = json.loads(sections)
    return NoteTemplate(
        id=r["id"],
        name=r["name"],
        description=r["description"],
        is_system=r["is_system"],
        owner_boss_id=r["owner_boss_id"],
        sections_json=sections or [],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


class NoteTemplatesRepo(BossScopedRepo):
    async def get(self, template_id: int) -> NoteTemplate | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT * FROM note_templates
                WHERE id=$1 AND (is_system=TRUE OR owner_boss_id=$2)
                """,
                template_id,
                self.ctx.boss_id,
            )
            return _row_to_template(row) if row else None

    async def list_visible(self) -> list[NoteTemplate]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM note_templates
                WHERE is_system=TRUE OR owner_boss_id=$1
                ORDER BY is_system DESC, name
                """,
                self.ctx.boss_id,
            )
            return [_row_to_template(r) for r in rows]

    async def insert_custom(
        self, name: str, description: str | None, sections: list[dict]
    ) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO note_templates (name, description, is_system, owner_boss_id,
                                            sections_json)
                VALUES ($1,$2,FALSE,$3,$4::jsonb) RETURNING id
                """,
                name,
                description,
                self.ctx.boss_id,
                json.dumps(sections),
            )
