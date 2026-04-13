from __future__ import annotations
from dataclasses import dataclass, field
from src import db as db_mod

_db = None

def init_context(database):
    global _db
    _db = database


@dataclass
class ChatContext:
    sender_chat_id: int
    sender_name: str
    sender_type: str          # boss | member | partner | unknown
    boss_chat_id: int
    boss_name: str
    lark_base_token: str
    lark_table_people: str
    lark_table_tasks: str
    lark_table_projects: str
    lark_table_ideas: str
    lark_table_reminders: str
    lark_table_notes: str
    chat_id: int
    is_group: bool
    group_name: str
    messages_collection: str
    tasks_collection: str
    all_memberships: list[dict] = field(default_factory=list)


async def resolve(chat_id: int, sender_id: int, is_group: bool,
                  preferred_boss_id: int | None = None) -> ChatContext | None:
    """
    Resolve context for a message. Returns None if user is unknown (needs onboarding).

    preferred_boss_id: if set, forces selection of that specific workspace.
    """
    # --- Group chat: resolve via group_map ---
    if is_group:
        group = await db_mod.get_group(_db, chat_id)
        if not group:
            return None
        boss = await db_mod.get_boss(_db, group["boss_chat_id"])
        if not boss:
            return None
        membership = await db_mod.get_membership(_db, str(sender_id), str(boss["chat_id"]))
        sender_type = membership["person_type"] if membership else "unknown"
        sender_name = membership["name"] if membership else str(sender_id)
        return _build_ctx(
            boss=boss,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_type=sender_type,
            chat_id=chat_id,
            is_group=True,
            group_name=group.get("group_name", ""),
            all_memberships=[],
        )

    # --- Direct message ---
    memberships = await db_mod.get_memberships(_db, str(sender_id))

    # If sender is a boss, ensure their own workspace is in the list
    boss_self = await db_mod.get_boss(_db, str(sender_id))
    if boss_self and str(boss_self.get("chat_id", "")) == str(sender_id):
        self_m = {
            "chat_id": str(sender_id),
            "boss_chat_id": str(sender_id),
            "person_type": "boss",
            "name": boss_self["name"],
            "status": "active",
        }
        if not any(m["boss_chat_id"] == str(sender_id) for m in memberships):
            memberships = [self_m] + list(memberships)

    if not memberships:
        return None

    # Preferred workspace (explicit selection) — return None if not found, never fall through
    if preferred_boss_id is not None:
        m = next((m for m in memberships if m["boss_chat_id"] == str(preferred_boss_id)), None)
        if not m:
            return None
        boss = await db_mod.get_boss(_db, m["boss_chat_id"])
        if not boss:
            return None
        return _build_ctx(boss, sender_id, m["name"], m["person_type"],
                           chat_id, False, "", memberships)

    # Single workspace: use directly
    if len(memberships) == 1:
        m = memberships[0]
        boss = await db_mod.get_boss(_db, m["boss_chat_id"])
        if not boss:
            return None
        return _build_ctx(boss, sender_id, m["name"], m["person_type"],
                           chat_id, False, "", memberships)

    # Multiple workspaces: prefer boss's own workspace, else first
    primary = next((m for m in memberships if m["person_type"] == "boss"), memberships[0])
    boss = await db_mod.get_boss(_db, primary["boss_chat_id"])
    if not boss:
        return None
    return _build_ctx(boss, sender_id, primary["name"], primary["person_type"],
                       chat_id, False, "", memberships)


def _build_ctx(boss: dict, sender_id: int, sender_name: str, sender_type: str,
               chat_id: int, is_group: bool, group_name: str,
               all_memberships: list[dict]) -> ChatContext:
    bid = boss["chat_id"]
    return ChatContext(
        sender_chat_id=int(sender_id),
        sender_name=sender_name,
        sender_type=sender_type,
        boss_chat_id=int(bid),
        boss_name=boss["name"],
        lark_base_token=boss["lark_base_token"],
        lark_table_people=boss["lark_table_people"],
        lark_table_tasks=boss["lark_table_tasks"],
        lark_table_projects=boss["lark_table_projects"],
        lark_table_ideas=boss["lark_table_ideas"],
        lark_table_reminders=boss.get("lark_table_reminders", ""),
        lark_table_notes=boss.get("lark_table_notes", ""),
        chat_id=int(chat_id),
        is_group=is_group,
        group_name=group_name,
        messages_collection=f"messages_{bid}",
        tasks_collection=f"tasks_{bid}",
        all_memberships=all_memberships,
    )
