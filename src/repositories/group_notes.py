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

    async def get_by_chat(
        self, provider: str | None, chat_id: str | None = None
    ) -> GroupNote | None:
        """Lookup note by (provider, chat_id) when both given, or by chat_id only.

        Tools surface chat_id (provider-agnostic in the agent surface), so when
        ``chat_id`` is None and ``provider`` is provided, treat the first arg
        as chat_id (single-arg call from tools).
        """
        # Allow single-arg invocation: get_by_chat("g1") → chat_id="g1"
        if chat_id is None:
            chat_id = provider
            provider = None
        async with self.pool.acquire() as c:
            if provider is None:
                row = await c.fetchrow(
                    """
                    SELECT * FROM group_notes
                    WHERE boss_id=$1 AND chat_id=$2
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    self.ctx.boss_id,
                    chat_id,
                )
            else:
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

    async def list_all(self) -> list[GroupNote]:
        """List all notes for this boss across all statuses (for list_groups tool)."""
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT * FROM group_notes
                WHERE boss_id=$1
                ORDER BY updated_at DESC
                """,
                self.ctx.boss_id,
            )
            return [_row_to_group_note(r) for r in rows]

    async def get_or_create(
        self,
        provider: str,
        chat_id: str,
        group_name: str | None = None,
        template_id: int | None = None,
    ) -> GroupNote:
        existing = await self.get_by_chat(provider, chat_id)
        if existing is not None:
            return existing
        await self.insert(
            provider=provider,
            chat_id=chat_id,
            group_name=group_name,
            template_id=template_id,
        )
        got = await self.get_by_chat(provider, chat_id)
        assert got is not None
        return got

    async def ensure_tracked(
        self,
        provider: str,
        chat_id: str,
        group_name: str | None = None,
    ) -> None:
        """Đánh dấu nhóm được track cho boss hiện tại (gọi khi sếp nói câu đầu).

        - Chưa có row  -> tạo (is_active=TRUE, status='active').
        - status='left' -> reactivate (sếp quay lại nhóm).
        - status khác (vd 'paused' do tự tắt) -> GIỮ nguyên, không bật lại.
        """
        async with self.pool.acquire() as c:
            await c.execute(
                """
                INSERT INTO group_notes (boss_id, provider, chat_id, group_name)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (boss_id, provider, chat_id) DO UPDATE SET
                  is_active = CASE WHEN group_notes.status='left' THEN TRUE
                                   ELSE group_notes.is_active END,
                  status    = CASE WHEN group_notes.status='left' THEN 'active'
                                   ELSE group_notes.status END,
                  group_name = COALESCE(EXCLUDED.group_name, group_notes.group_name)
                """,
                self.ctx.boss_id, provider, chat_id, group_name,
            )

    async def bosses_tracking(self, provider: str, chat_id: str) -> list[int]:
        """Cross-boss: các boss đang track (is_active) nhóm này. Dùng bởi InboundIngest."""
        async with self.pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT boss_id FROM group_notes
                WHERE provider=$1 AND chat_id=$2 AND is_active
                ORDER BY boss_id
                """,
                provider, chat_id,
            )
        return [r["boss_id"] for r in rows]

    async def mark_left(self, boss_id: int, provider: str, chat_id: str) -> None:
        """Cross-boss: sếp rời nhóm -> deactivate (status='left'). Dùng bởi re-verify job."""
        async with self.pool.acquire() as c:
            await c.execute(
                """
                UPDATE group_notes SET is_active=FALSE, status='left', updated_at=NOW()
                WHERE boss_id=$1 AND provider=$2 AND chat_id=$3
                """,
                boss_id, provider, chat_id,
            )

    async def update_after_note_rebuild(
        self,
        group_note_id: int,
        content: str,
        last_seen_message_id: int,
        emitted_by: str,
    ) -> int:
        """Update content + last_seen_message_id atomically, write version. Returns new version number."""
        async with self.pool.acquire() as c:
            async with c.transaction():
                await c.execute(
                    """
                    UPDATE group_notes
                    SET content=$2, last_seen_message_id=$3, updated_at=NOW()
                    WHERE id=$1 AND boss_id=$4
                    """,
                    group_note_id,
                    content,
                    last_seen_message_id,
                    self.ctx.boss_id,
                )
                version_id = await c.fetchval(
                    """
                    INSERT INTO group_note_versions (group_note_id, content, emitted_by)
                    VALUES ($1,$2,$3) RETURNING id
                    """,
                    group_note_id,
                    content,
                    emitted_by,
                )
                return version_id

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
