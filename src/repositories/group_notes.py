import json

import asyncpg

from src.domain.group_note import GroupNote
from src.repositories.base import BossScopedRepo


def _row_to_group_note(r: asyncpg.Record) -> GroupNote:
    manually_edited = r["manually_edited_sections"]
    if isinstance(manually_edited, str):
        manually_edited = json.loads(manually_edited)
    return GroupNote(
        id=r["id"],
        boss_id=r["boss_id"],
        provider=r["provider"],
        chat_id=r["chat_id"],
        group_name=r["group_name"],
        content=r["content"],
        manually_edited_sections=manually_edited or [],
        last_seen_message_id=r["last_seen_message_id"],
        status=r["status"],
        msg_count_7d=r["msg_count_7d"],
        template_id=r["template_id"],
        updated_at=r["updated_at"],
        created_at=r["created_at"],
    )


class GroupNotesRepo(BossScopedRepo):
    async def get(self, group_note_id: int) -> GroupNote | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                "SELECT * FROM group_notes WHERE id=$1 AND boss_id=$2",
                group_note_id,
                self.ctx.boss_id,
            )
            return _row_to_group_note(row) if row else None

    async def get_by_chat(self, provider: str, chat_id: str) -> GroupNote | None:
        async with self.pool.acquire() as c:
            row = await c.fetchrow(
                """
                SELECT * FROM group_notes
                WHERE boss_id=$1 AND provider=$2 AND chat_id=$3
                """,
                self.ctx.boss_id,
                provider,
                chat_id,
            )
            return _row_to_group_note(row) if row else None

    async def list(self, status: str = "active") -> list[GroupNote]:
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM group_notes
                WHERE boss_id=$1 AND status=$2
                ORDER BY updated_at DESC
                """,
                self.ctx.boss_id,
                status,
            )
            return [_row_to_group_note(r) for r in rows]

    async def insert(
        self,
        provider: str,
        chat_id: str,
        group_name: str | None,
        template_id: int | None = None,
    ) -> int:
        async with self.pool.acquire() as c:
            return await c.fetchval(
                """
                INSERT INTO group_notes (boss_id, provider, chat_id, group_name, template_id)
                VALUES ($1,$2,$3,$4,$5)
                ON CONFLICT (boss_id, provider, chat_id) DO UPDATE SET
                  group_name=EXCLUDED.group_name
                RETURNING id
                """,
                self.ctx.boss_id,
                provider,
                chat_id,
                group_name,
                template_id,
            )

    async def update_content(self, group_note_id: int, content: str, emitted_by: str) -> None:
        async with self.pool.acquire() as c:
            async with c.transaction():
                await c.execute(
                    """
                    UPDATE group_notes SET content=$2, updated_at=NOW()
                    WHERE id=$1 AND boss_id=$3
                    """,
                    group_note_id,
                    content,
                    self.ctx.boss_id,
                )
                await c.execute(
                    """
                    INSERT INTO group_note_versions (group_note_id, content, emitted_by)
                    VALUES ($1,$2,$3)
                    """,
                    group_note_id,
                    content,
                    emitted_by,
                )
