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
    # memberships is the raw DB rows list — each row has chat_id = sender_id by query design.
    # The synthetic boss entry also has chat_id = sender_id. So sender_m always finds a row.
    sender_m = next(
        (m for m in memberships if str(m.get("chat_id", "")) == str(sender_id)),
        None,
    )
    if sender_m and sender_m.get("language"):
        return sender_m["language"]
    if primary and primary.get("language"):
        return primary["language"]
    return "en"


async def build_group_context(group_chat_id: int, boss_chat_id: int) -> dict:
    """
    Builds group-specific context dict:
    {
        "group_name": str,
        "project": {"name": str, "status": str} | None,
        "group_note": str | None,
        "recent_participants": [str, ...],
        "active_topic": str,
    }
    """
    from src.services import lark as _lark

    _db = await db.get_db()

    # group_name + project_id from group_map
    async with _db.execute(
        "SELECT group_name, project_id FROM group_map WHERE group_chat_id = ?",
        (group_chat_id,),
    ) as cur:
        row = await cur.fetchone()
    group_name = row["group_name"] if row else ""
    project_id = row["project_id"] if row else None

    # Fetch project info from Lark if linked
    project = None
    if project_id:
        boss = await db.get_boss(boss_chat_id)
        if boss:
            try:
                table = boss.get("lark_table_projects", "")
                if table:
                    records = await _lark.search_records(boss["lark_base_token"], table)
                    match = next((r for r in records if r.get("record_id") == project_id), None)
                    if match:
                        project = {
                            "name": match.get("Tên dự án", match.get("Name", "")),
                            "status": match.get("Trạng thái", match.get("Status", "")),
                        }
            except Exception:
                pass

    # Group note
    note_row = await db.get_note(boss_chat_id, "group", str(group_chat_id))
    group_note = note_row.get("content") if note_row else None

    # Recent participants: get distinct sender_ids from last 15 messages, look up names
    async with _db.execute(
        "SELECT DISTINCT sender_id FROM messages WHERE chat_id = ? AND sender_id IS NOT NULL ORDER BY id DESC LIMIT 15",
        (group_chat_id,),
    ) as cur:
        sender_rows = await cur.fetchall()

    recent_participants = []
    for sr in sender_rows:
        sid = sr["sender_id"]
        async with _db.execute(
            "SELECT name FROM memberships WHERE chat_id = ?",
            (str(sid),),
        ) as cur2:
            m = await cur2.fetchone()
        if m and m["name"]:
            recent_participants.append(m["name"])
        else:
            boss_row = await db.get_boss(sid)
            if boss_row:
                recent_participants.append(boss_row["name"])

    # Active topic — LLM mini-call on last 10 messages
    async with _db.execute(
        "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT 10",
        (group_chat_id,),
    ) as cur:
        msg_rows = await cur.fetchall()
    active_topic = await _get_active_topic(list(reversed([dict(r) for r in msg_rows])))

    return {
        "group_name": group_name,
        "project": project,
        "group_note": group_note,
        "recent_participants": recent_participants,
        "active_topic": active_topic,
    }


async def _get_active_topic(messages: list[dict]) -> str:
    """LLM mini-call: summarize what the group is currently discussing in 1 sentence."""
    if not messages:
        return ""
    from src.services import openai_client as _oai
    conversation = "\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
    )
    response, _ = await _oai.chat_with_tools(
        [
            {
                "role": "system",
                "content": "Tóm tắt trong 1 câu ngắn chủ đề mà nhóm đang bàn luận. Chỉ trả về câu tóm tắt, không giải thích thêm.",
            },
            {"role": "user", "content": conversation},
        ],
        [],
    )
    return (response.content or "").strip()


def membership_summary(memberships: list) -> str:
    """Returns a short string like 'Company A (boss), Company B (partner)' for system prompt."""
    if not memberships:
        return "(no workspaces)"
    return ", ".join(f"{m['workspace']} ({m['role']})" for m in memberships)
