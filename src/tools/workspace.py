"""
workspace.py — Workspace and language preference tools.
"""
from src import db
from src.context import ChatContext


async def set_language(ctx: ChatContext, language_code: str) -> str:
    """Persist language preference for this sender."""
    _db = await db.get_db()
    # Update memberships.language for this sender in active workspace
    await _db.execute(
        "UPDATE memberships SET language = ? WHERE chat_id = ? AND boss_chat_id = ?",
        (language_code, str(ctx.sender_chat_id), str(ctx.boss_chat_id)),
    )
    # If sender is boss, also update bosses.language
    if ctx.sender_type == "boss":
        await _db.execute(
            "UPDATE bosses SET language = ? WHERE chat_id = ?",
            (language_code, ctx.boss_chat_id),
        )
    await _db.commit()
    return f"Language set to '{language_code}'."


async def switch_workspace(ctx: ChatContext, boss_id: int) -> str:
    """
    Switch active workspace. Preference persisted for 30 min.
    Secretary will use this workspace for subsequent messages.
    """
    # Verify user has access to this workspace
    memberships = await db.get_memberships(str(ctx.sender_chat_id))
    boss_self = await db.get_boss(ctx.sender_chat_id)
    valid_ids = {m["boss_chat_id"] for m in memberships}
    if boss_self:
        valid_ids.add(str(ctx.sender_chat_id))

    if str(boss_id) not in valid_ids:
        return f"You don't have access to workspace {boss_id}."

    await db.set_session(ctx.sender_chat_id, "preferred_workspace", str(boss_id), ttl_minutes=30)

    boss = await db.get_boss(boss_id)
    company = boss.get("company", str(boss_id)) if boss else str(boss_id)
    return f"Switched to workspace: {company}. This preference lasts 30 minutes."
