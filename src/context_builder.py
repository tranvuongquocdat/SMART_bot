"""
context_builder.py — Pure Python context assembly. No LLM call.
Runs before Secretary. Returns structured context dict.
"""
import json
import logging
from datetime import datetime, timezone

from src import db

logger = logging.getLogger("context_builder")


async def build(sender_id: int, chat_id: int) -> dict:
    """
    Returns:
    {
        "sender_id": int,
        "memberships": [{"workspace": str, "boss_id": int, "role": str, "language": str|None}],
        "active_sessions": {"reset_pending": dict|None, "join_pending": [...], "approvals_pending": [...]},
        "last_5_messages": [...],
        "primary_workspace_id": int | None,
        "language": str,
    }
    """
    memberships = await db.get_memberships(str(sender_id))

    # Include boss's own workspace if they are a boss
    boss_self = await db.get_boss(sender_id)
    if boss_self and not any(m["boss_chat_id"] == str(sender_id) for m in memberships):
        memberships = [{
            "chat_id": str(sender_id),
            "boss_chat_id": str(sender_id),
            "person_type": "boss",
            "name": boss_self["name"],
            "status": "active",
            "language": boss_self.get("language", "en"),
        }] + list(memberships)

    resolved = []
    for m in memberships:
        boss = await db.get_boss(m["boss_chat_id"])
        if boss:
            resolved.append({
                "workspace": boss.get("company", str(m["boss_chat_id"])),
                "boss_id": int(m["boss_chat_id"]),
                "role": m["person_type"],
                "language": m.get("language"),
            })

    primary = next(
        (m for m in resolved if m["role"] == "boss"),
        resolved[0] if resolved else None
    )
    primary_id = primary["boss_id"] if primary else None

    # Check preferred workspace from sessions (switch_workspace with TTL)
    preferred_raw = await db.get_session(sender_id, "preferred_workspace")
    if preferred_raw:
        try:
            preferred_id = int(preferred_raw)
            if any(m["boss_id"] == preferred_id for m in resolved):
                primary_id = preferred_id
        except ValueError:
            pass

    active_sessions = await _get_active_sessions(sender_id)
    last_5 = await db.get_recent(chat_id, limit=5)
    language = _resolve_language(memberships, sender_id, primary)

    return {
        "sender_id": sender_id,
        "memberships": resolved,
        "active_sessions": active_sessions,
        "last_5_messages": last_5,
        "primary_workspace_id": primary_id,
        "language": language,
    }


async def _get_active_sessions(sender_id: int) -> dict:
    reset_raw = await db.get_session(sender_id, "reset_step")
    reset_pending = json.loads(reset_raw) if reset_raw else None

    _db = await db.get_db()

    # Join requests this user sent (pending)
    async with _db.execute(
        "SELECT * FROM memberships WHERE chat_id = ? AND status = 'pending'",
        (str(sender_id),),
    ) as cur:
        rows = await cur.fetchall()
    join_pending = [dict(r) for r in rows]

    # Approvals this user (as boss) needs to handle
    approvals_pending = []
    async with _db.execute(
        "SELECT *, 'join' AS approval_type FROM memberships WHERE boss_chat_id = ? AND status = 'pending'",
        (str(sender_id),),
    ) as cur:
        rows = await cur.fetchall()
    approvals_pending.extend([dict(r) for r in rows])

    async with _db.execute(
        "SELECT *, 'task' AS approval_type FROM pending_approvals WHERE boss_chat_id = ? AND status = 'pending'",
        (str(sender_id),),
    ) as cur:
        rows = await cur.fetchall()
    approvals_pending.extend([dict(r) for r in rows])

    return {
        "reset_pending": reset_pending,
        "join_pending": join_pending,
        "approvals_pending": approvals_pending,
    }


def _resolve_language(memberships: list, sender_id: int, primary: dict | None) -> str:
    sender_m = next(
        (m for m in memberships if str(m.get("chat_id", "")) == str(sender_id)),
        None,
    )
    if sender_m and sender_m.get("language"):
        return sender_m["language"]
    if primary and primary.get("language"):
        return primary["language"]
    return "en"


def membership_summary(memberships: list) -> str:
    """Returns a short string like 'Company A (boss), Company B (partner)' for system prompt."""
    if not memberships:
        return "(no workspaces)"
    return ", ".join(f"{m['workspace']} ({m['role']})" for m in memberships)
