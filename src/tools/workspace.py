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


async def switch_workspace(ctx: ChatContext, workspace: str = "", boss_id: int = 0) -> str:
    """
    Switch active workspace. Persists active_workspace_id in memberships table.
    Accepts workspace name (fuzzy match) or boss_id integer.
    """
    from src.tools._workspace import set_active_workspace_id, resolve_workspaces
    all_ws = await resolve_workspaces(ctx, "all")

    if not all_ws:
        return "Bạn chưa thuộc workspace nào."

    # Match by name or by boss_id
    match = None
    if workspace:
        match = next((w for w in all_ws if workspace.lower() in w["workspace_name"].lower()), None)
    elif boss_id:
        match = next((w for w in all_ws if w["boss_id"] == boss_id), None)

    if not match:
        names = ", ".join(w["workspace_name"] for w in all_ws)
        return f"Không tìm thấy workspace '{workspace or boss_id}'. Có: {names}"

    await set_active_workspace_id(ctx.sender_chat_id, str(match["boss_id"]))
    return f"Đã chuyển sang workspace: {match['workspace_name']}"
