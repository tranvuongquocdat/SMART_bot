"""
join.py — LLM-native join flow tools.
Replaces keyword-based join state machine in agent.py and onboarding.py.
"""
import logging

from src import db
from src.context import ChatContext
from src.services import lark, telegram

logger = logging.getLogger("tools.join")


async def list_available_workspaces(ctx: ChatContext) -> str:
    """Returns workspaces this user can join (not already an active member)."""
    all_bosses = await db.get_all_bosses()
    memberships = await db.get_memberships(str(ctx.sender_chat_id))
    active_boss_ids = {m["boss_chat_id"] for m in memberships}
    # Also exclude own workspace
    active_boss_ids.add(str(ctx.sender_chat_id))

    available = [b for b in all_bosses if str(b["chat_id"]) not in active_boss_ids]
    if not available:
        return "No other workspaces available to join at this time."

    lines = ["Available workspaces:"]
    for i, b in enumerate(available, 1):
        lines.append(f"{i}. {b['company']} (boss: {b['name']}) — boss_id: {b['chat_id']}")
    return "\n".join(lines)


async def request_join(ctx: ChatContext, target_boss_id: int, role: str, intro: str) -> str:
    """Creates a pending membership and notifies the target boss."""
    _db = await db.get_db()

    await db.upsert_membership(
        _db,
        chat_id=str(ctx.sender_chat_id),
        boss_chat_id=str(target_boss_id),
        person_type=role,
        name=ctx.sender_name,
        status="pending",
        request_info=intro,
    )

    boss = await db.get_boss(target_boss_id)
    if not boss:
        return f"Could not find workspace for boss_id {target_boss_id}."

    company = boss.get("company", str(target_boss_id))
    notify_msg = (
        f"Join request from {ctx.sender_name} (chat_id={ctx.sender_chat_id}):\n"
        f"Role requested: {role}\n"
        f"Introduction: {intro}\n\n"
        f"Reply naturally to approve or reject (e.g. 'approve', 'ok partner', 'reject')."
    )
    try:
        await telegram.send(target_boss_id, notify_msg)
    except Exception:
        logger.exception("Failed to notify boss %s of join request", target_boss_id)

    return f"Join request sent to {company}. You'll be notified when the boss responds."


async def approve_join(ctx: ChatContext, membership_chat_id: str, role: str = None) -> str:
    """
    Approve a join request. Writes person to Lark People table of THIS workspace.
    ctx must be the target boss's context.
    """
    _db = await db.get_db()
    membership = await db.get_membership(_db, str(membership_chat_id), str(ctx.boss_chat_id))
    if not membership or membership["status"] != "pending":
        return f"No pending join request found for chat_id={membership_chat_id}."

    person_type = role or membership["person_type"]
    name = membership["name"] or "Unknown"

    # Write to Lark People table of THIS workspace (the boss's workspace) ← BUG FIX
    fields = {
        "Tên": name,
        "Chat ID": int(membership_chat_id),
        "Type": person_type,
        "Ghi chú": membership.get("request_info", ""),
    }
    try:
        rec = await lark.create_record(ctx.lark_base_token, ctx.lark_table_people, fields)
        lark_record_id = rec.get("record_id", "")
    except Exception:
        logger.exception("Failed to write to Lark People for membership %s", membership_chat_id)
        lark_record_id = ""

    await db.upsert_membership(
        _db,
        chat_id=str(membership_chat_id),
        boss_chat_id=str(ctx.boss_chat_id),
        person_type=person_type,
        name=name,
        status="active",
        lark_record_id=lark_record_id,
    )

    company = ctx.boss_name
    try:
        await telegram.send(
            int(membership_chat_id),
            f"Your request to join {company} has been approved as {person_type}. "
            f"You can now interact with the AI secretary for {company}.",
        )
    except Exception:
        logger.exception("Failed to notify approved member %s", membership_chat_id)

    return f"Approved {name} as {person_type} in {company}."


async def reject_join(ctx: ChatContext, membership_chat_id: str) -> str:
    """Reject a join request and notify the requester."""
    _db = await db.get_db()
    membership = await db.get_membership(_db, str(membership_chat_id), str(ctx.boss_chat_id))
    if not membership or membership["status"] != "pending":
        return f"No pending join request found for chat_id={membership_chat_id}."

    await db.upsert_membership(
        _db,
        chat_id=str(membership_chat_id),
        boss_chat_id=str(ctx.boss_chat_id),
        person_type=membership["person_type"],
        name=membership["name"],
        status="rejected",
    )

    company = ctx.boss_name
    try:
        await telegram.send(
            int(membership_chat_id),
            f"Your request to join {company} was not approved.",
        )
    except Exception:
        pass

    return f"Rejected join request from chat_id={membership_chat_id}."
