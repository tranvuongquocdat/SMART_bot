"""Re-verify nhóm đang track: nếu acc chính của sếp không còn trong nhóm -> deactivate.

DUY NHẤT chỗ dùng list_members — để TẮT, không phải để bật (bật vẫn boss-spoke).
Gate theo capabilities.member.list_api: kênh không hỗ trợ -> bỏ qua.
"""

from __future__ import annotations

import logging
from typing import Any

from src.channels.capabilities import caps_for
from src.repositories.base import BossContext
from src.repositories.group_notes import GroupNotesRepo

log = logging.getLogger(__name__)

_SUPER = BossContext(boss_id=0, user_role="superadmin")


class _Acc:
    """Duck-typed bot_account đủ cho adapter.list_members (cần .id, .owner_boss_id)."""

    def __init__(self, bot_account_id: int):
        self.id = bot_account_id
        self.owner_boss_id = None


async def reverify_once(pool, registry) -> None:
    repo = GroupNotesRepo(pool, _SUPER)
    for adapter in registry.adapters():
        provider = adapter.provider
        if not caps_for(provider).get("member.list_api"):
            continue
        async with pool.acquire() as c:
            rows = await c.fetch(
                """
                SELECT gn.boss_id, gn.chat_id, al.provider_user_id AS boss_uid,
                       baa.bot_account_id
                FROM group_notes gn
                JOIN account_links al
                  ON al.boss_id = gn.boss_id AND al.provider = gn.provider
                JOIN bot_account_assignments baa
                  ON baa.boss_id = gn.boss_id AND baa.provider = gn.provider
                     AND baa.status='active'
                WHERE gn.provider=$1 AND gn.is_active
                """,
                provider,
            )
        for r in rows:
            try:
                members = await adapter.list_members(
                    _Acc(r["bot_account_id"]), r["chat_id"]
                )
            except Exception:
                log.exception(
                    "reverify list_members failed provider=%s chat=%s",
                    provider, r["chat_id"],
                )
                continue
            if r["boss_uid"] not in set(map(str, members)):
                await repo.mark_left(r["boss_id"], provider, r["chat_id"])


async def job(app_state: Any) -> None:
    registry = getattr(app_state, "channel_registry", None)
    if registry is None:
        return
    await reverify_once(app_state.db_pool, registry)
