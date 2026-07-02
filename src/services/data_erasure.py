"""DataErasure — xoá dữ liệu THẬT (PDPL right-to-erasure).

Hai mức:
  - ``erase_group``: xoá mọi dữ liệu một nhóm cho một boss (UI "Xoá nhóm").
  - ``erase_boss``: xoá toàn bộ dữ liệu một boss (superadmin, có audit).

Nguyên tắc: Postgres + Qdrant cùng sạch trong một lần gọi; trả counts để
audit. Users row KHÔNG xoá mà anonymize — giữ FK integrity (audit log,
billing) trong khi dữ liệu cá nhân thực sự biến mất.

Spec: docs/superpowers/specs/2026-07-02-compliance-erasure-retention-design.md
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

QDRANT_COLLECTION = "smart_bot"


def _qdrant_filter(conds: list[dict]) -> object:
    from qdrant_client import models

    return models.FilterSelector(
        filter=models.Filter(
            must=[
                models.FieldCondition(
                    key=c["key"], match=models.MatchValue(value=c["value"])
                )
                for c in conds
            ]
        )
    )


class DataErasure:
    def __init__(self, pool, qdrant=None):
        self.pool = pool
        self.qdrant = qdrant

    async def _qdrant_delete(self, conds: list[dict]) -> None:
        if self.qdrant is None:
            return
        try:
            await self.qdrant.delete(
                collection_name=QDRANT_COLLECTION,
                points_selector=_qdrant_filter(conds),
            )
        except Exception:
            # Qdrant lỗi không được chặn erasure Postgres; index mồ côi không
            # retrieval được (join DB fail) nhưng vẫn log để dọn tay.
            log.exception("qdrant delete failed conds=%s", conds)

    async def erase_group(self, boss_id: int, provider: str, chat_id: str) -> dict[str, int]:
        """Xoá mọi dữ liệu một nhóm cho boss này. Nhóm/boss khác không đụng."""
        await self._qdrant_delete([
            {"key": "boss_id", "value": boss_id},
            {"key": "chat_id", "value": chat_id},
        ])
        counts: dict[str, int] = {}
        async with self.pool.acquire() as c:
            async with c.transaction():
                for name, sql, args in [
                    ("knowledge_items",
                     "DELETE FROM knowledge_items WHERE boss_id=$1 AND chat_id=$2",
                     (boss_id, chat_id)),
                    ("messages",
                     "DELETE FROM messages WHERE boss_id=$1 AND provider=$2 AND chat_id=$3",
                     (boss_id, provider, chat_id)),
                    ("outbound_messages",
                     "DELETE FROM outbound_messages WHERE boss_id=$1 AND provider=$2 AND chat_id=$3",
                     (boss_id, provider, chat_id)),
                    ("scheduled_reminders",
                     "DELETE FROM scheduled_reminders WHERE boss_id=$1 AND chat_id=$2",
                     (boss_id, chat_id)),
                    # Con của group_notes (pins/action_items/members/versions/
                    # summaries/decisions/artifacts) CASCADE theo row này.
                    ("group_notes",
                     "DELETE FROM group_notes WHERE boss_id=$1 AND provider=$2 AND chat_id=$3",
                     (boss_id, provider, chat_id)),
                ]:
                    status = await c.execute(sql, *args)
                    counts[name] = int(status.split()[-1])
        log.info("erase_group boss=%s chat=%s counts=%s", boss_id, chat_id, counts)
        return counts

    async def erase_boss(self, boss_id: int) -> dict[str, int]:
        """Right-to-erasure toàn bộ một boss. Users row anonymize, không xoá."""
        await self._qdrant_delete([{"key": "boss_id", "value": boss_id}])
        counts: dict[str, int] = {}
        async with self.pool.acquire() as c:
            async with c.transaction():
                # Thứ tự FK-safe: bảng phụ thuộc trước, nguồn tham chiếu sau.
                simple = [
                    # group_notes sớm — cascade dọn pins/action_items/members/…
                    ("group_notes", "DELETE FROM group_notes WHERE boss_id=$1"),
                    ("knowledge_items", "DELETE FROM knowledge_items WHERE boss_id=$1"),
                    ("messages", "DELETE FROM messages WHERE boss_id=$1"),
                    ("outbound_messages", "DELETE FROM outbound_messages WHERE boss_id=$1"),
                    ("scheduled_reminders", "DELETE FROM scheduled_reminders WHERE boss_id=$1"),
                    ("memory_entries", "DELETE FROM memory_entries WHERE boss_id=$1"),
                    ("action_items", "DELETE FROM action_items WHERE boss_id=$1"),
                    ("projects", "DELETE FROM projects WHERE boss_id=$1"),
                    ("notifications", "DELETE FROM notifications WHERE boss_id=$1"),
                    ("account_links", "DELETE FROM account_links WHERE boss_id=$1"),
                    ("linking_tokens", "DELETE FROM linking_tokens WHERE boss_id=$1"),
                    ("boss_active_tools", "DELETE FROM boss_active_tools WHERE boss_id=$1"),
                    ("boss_integrations", "DELETE FROM boss_integrations WHERE boss_id=$1"),
                    ("mcp_servers", "DELETE FROM mcp_servers WHERE boss_id=$1"),
                    ("integration_usage", "DELETE FROM integration_usage WHERE boss_id=$1"),
                    ("token_usage", "DELETE FROM token_usage WHERE boss_id=$1"),
                    ("tool_call_log", "DELETE FROM tool_call_log WHERE boss_id=$1"),
                    ("subscription_requests", "DELETE FROM subscription_requests WHERE boss_id=$1"),
                    ("bot_account_assignments", "DELETE FROM bot_account_assignments WHERE boss_id=$1"),
                    ("bot_accounts", "DELETE FROM bot_accounts WHERE owner_boss_id=$1"),
                    # web identity (web_group_members cascade theo web_users)
                    ("web_users", "DELETE FROM web_users WHERE boss_user_id=$1"),
                ]
                for name, sql in simple:
                    status = await c.execute(sql, boss_id)
                    counts[name] = int(status.split()[-1])
                await c.execute(
                    """
                    UPDATE users
                       SET email = 'erased-' || id || '@erased.invalid',
                           name = NULL, password_hash = NULL, google_sub = NULL,
                           api_keys_enc = NULL, ai_key_status = '{}'::jsonb,
                           ai_provider_urls = '{}'::jsonb,
                           subscription_status = 'erased'
                     WHERE id=$1
                    """,
                    boss_id,
                )
                counts["users_anonymized"] = 1
        log.info("erase_boss boss=%s counts=%s", boss_id, counts)
        return counts
