"""
join.py — LLM-native join flow tools.
Replaces keyword-based join state machine in agent.py and onboarding.py.
"""
import logging

from src import db
from src.repositories.boss_repo import BossRepo
from src.context import ChatContext
from src.channels import telegram_singleton as telegram
from src.infrastructure import lark_client as lark
from src.services import membership_service
from src.repositories.membership_repo import MembershipRepo

logger = logging.getLogger("tools.join")


async def list_available_workspaces(ctx: ChatContext) -> str:
    """Returns workspaces this user can join (not already an active member)."""
    all_bosses = await (await db._repo("boss", BossRepo)).list_all()
    memberships = await (await db._repo("membership", MembershipRepo)).list_for_user(str(ctx.sender_chat_id))
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


async def request_join(ctx: ChatContext, target_boss_id: str, role: str, intro: str) -> str:
    """Creates a pending membership and notifies the target boss."""
    _db = await db.get_db()

    await (await db._repo("membership", MembershipRepo)).upsert(
        _db,
        chat_id=str(ctx.sender_chat_id),
        boss_chat_id=str(target_boss_id),
        person_type=role,
        name=ctx.sender_name,
        status="pending",
        request_info=intro,
    )

    boss = await (await db._repo("boss", BossRepo)).get(target_boss_id)
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
    """Approve a join request. Routes the write through membership_service.activate()."""
    _db = await db.get_db()
    membership = await MembershipRepo(_db).get(str(membership_chat_id), str(ctx.boss_chat_id))
    if not membership or membership["status"] != "pending":
        return f"No pending join request found for chat_id={membership_chat_id}."

    person_type = role or membership["person_type"]
    name = membership["name"] or "Unknown"
    request_info = membership.get("request_info", "")

    await membership_service.activate(
        chat_id=str(membership_chat_id),
        boss_chat_id=str(ctx.boss_chat_id),
        person_type=person_type,
        name=name,
        source="approval",
        request_info=request_info,
    )

    company = ctx.boss_name
    # Notify the stranger on their own channel. Failure here is non-fatal —
    # boss still gets the success string; we just log so the gap is visible.
    try:
        role_label = "thành viên" if person_type == "member" else "đối tác"
        msg = (
            f"Yêu cầu tham gia *{company}* đã được duyệt với vai trò *{role_label}*. "
            f"Bạn có thể bắt đầu nhắn việc / hỏi bot ngay."
        )
        await telegram.send(str(membership_chat_id), msg)
    except Exception:
        logger.exception("approve_join: failed to notify stranger %s", membership_chat_id)

    return f"Approved {name} as {person_type} in {company}."


async def reject_join(ctx: ChatContext, membership_chat_id: str) -> str:
    """Reject a join request and notify the requester."""
    _db = await db.get_db()
    membership = await MembershipRepo(_db).get(str(membership_chat_id), str(ctx.boss_chat_id))
    if not membership or membership["status"] != "pending":
        return f"No pending join request found for chat_id={membership_chat_id}."

    await (await db._repo("membership", MembershipRepo)).upsert(
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
            membership_chat_id,
            f"Your request to join {company} was not approved.",
        )
    except Exception:
        pass

    return f"Rejected join request from chat_id={membership_chat_id}."
