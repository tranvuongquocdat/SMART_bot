"""Drop noisy Zalo inbound *before* save/embed/agent.

Zalo (unlike Telegram bot tokens) uses a personal account — the same one
the user normally chats with friends on. Without filtering, every group
message and every random DM goes through the agent pipeline, costs
embeddings, and fills the DB with noise.

Forward-rules:
  DM:
    - sender is a registered Zalo boss            → forward
    - text contains the onboard phrase            → forward (lets a sếp
                                                    introduce themselves)
    - else                                        → drop
  Group:
    - group already in `group_map`                → forward
    - bot is @mentioned by a registered boss      → forward (so the boss
                                                    can register the group)
    - else                                        → drop

Zalo-only logic. Telegram has its own clean separation (bot token).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("channels.zalo.filter")


class ZaloInboundFilter:
    def __init__(self, onboard_phrase: str) -> None:
        self._phrase = (onboard_phrase or "").strip().lower()

    async def should_forward(self, ev: dict) -> bool:
        thread_type = ev.get("thread_type")
        sender_uid = str(ev.get("sender_uid", "") or "").strip()
        thread_id = str(ev.get("thread_id", "") or "").strip()
        text = (ev.get("text") or "").strip().lower()
        is_mentioned = bool(ev.get("is_mentioned"))

        if thread_type == "dm":
            if await self._is_zalo_boss(sender_uid):
                return True
            if self._phrase and self._phrase in text:
                logger.info("zalo.filter: onboard phrase matched, forwarding DM")
                return True
            return False

        if thread_type == "group":
            if await self._is_registered_group(thread_id):
                return True
            if is_mentioned and await self._is_zalo_boss(sender_uid):
                return True
            return False

        return False

    @staticmethod
    async def _is_zalo_boss(zalo_uid: str) -> bool:
        if not zalo_uid:
            return False
        from src import db
        person_id = await db.lookup_person_by_external("zalo", zalo_uid)
        if not person_id:
            return False
        return (await db.get_boss(person_id)) is not None

    @staticmethod
    async def _is_registered_group(zalo_thread_id: str) -> bool:
        if not zalo_thread_id:
            return False
        from src import db
        conv_id = await db.lookup_conversation_by_external("zalo", zalo_thread_id)
        if not conv_id:
            return False
        return (await db.get_group(conv_id)) is not None
