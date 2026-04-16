"""
_workspace.py — Shared cross-workspace credential resolution.
Used by tools that accept workspace_ids parameter.
"""
from src import db
from src.context import ChatContext


async def resolve_workspaces(ctx: ChatContext, workspace_ids: str | list) -> list[dict]:
    """
    Returns list of workspace credential dicts.
    Each dict has: boss_id, lark_base_token, lark_table_people, lark_table_tasks,
                   lark_table_projects, lark_table_ideas, workspace_name, user_role.

    workspace_ids:
        "current"  — only active workspace (respects active_workspace_id if set)
        "all"      — all workspaces user belongs to
        "primary"  — boss's own workspace regardless of active setting
        [id, ...]  — specific boss_ids
    """
    if workspace_ids == "primary":
        return [_ctx_to_workspace(ctx)]

    if workspace_ids == "current":
        # Check if user has an active_workspace_id set (from switch_workspace)
        active_ws_id = await _get_active_workspace_id(ctx.sender_chat_id)
        if active_ws_id and active_ws_id != str(ctx.boss_chat_id):
            boss = await db.get_boss(int(active_ws_id))
            if boss:
                return [_boss_to_workspace(boss, ctx.sender_type)]
        return [_ctx_to_workspace(ctx)]

    memberships = await db.get_memberships(str(ctx.sender_chat_id))
    # Include own boss workspace
    boss_self = await db.get_boss(ctx.sender_chat_id)
    if boss_self and not any(m["boss_chat_id"] == str(ctx.sender_chat_id) for m in memberships):
        memberships = [{
            "boss_chat_id": str(ctx.sender_chat_id),
            "person_type": "boss",
            "status": "active",
        }] + list(memberships)

    active_memberships = [m for m in memberships if m.get("status") == "active"]

    if workspace_ids != "all":
        target_ids = [str(i) for i in (workspace_ids if isinstance(workspace_ids, list) else [workspace_ids])]
        active_memberships = [m for m in active_memberships if m["boss_chat_id"] in target_ids]

    result = []
    for m in active_memberships:
        boss = await db.get_boss(m["boss_chat_id"])
        if boss:
            result.append(_boss_to_workspace(boss, m.get("person_type", "member")))
    return result


async def _get_active_workspace_id(sender_chat_id: int) -> str | None:
    _db = await db.get_db()
    async with _db.execute(
        "SELECT active_workspace_id FROM memberships WHERE chat_id = ? AND active_workspace_id IS NOT NULL LIMIT 1",
        (str(sender_chat_id),),
    ) as cur:
        row = await cur.fetchone()
    return row["active_workspace_id"] if row else None


async def set_active_workspace_id(sender_chat_id: int, boss_chat_id: str) -> None:
    _db = await db.get_db()
    await _db.execute(
        "UPDATE memberships SET active_workspace_id = ? WHERE chat_id = ?",
        (boss_chat_id, str(sender_chat_id)),
    )
    await _db.commit()


def _boss_to_workspace(boss: dict, user_role: str) -> dict:
    return {
        "boss_id": int(boss["chat_id"]),
        "workspace_name": boss.get("company", str(boss["chat_id"])),
        "user_role": user_role,
        "lark_base_token": boss["lark_base_token"],
        "lark_table_people": boss.get("lark_table_people", ""),
        "lark_table_tasks": boss.get("lark_table_tasks", ""),
        "lark_table_projects": boss.get("lark_table_projects", ""),
        "lark_table_ideas": boss.get("lark_table_ideas", ""),
        "lark_table_reminders": boss.get("lark_table_reminders", ""),
        "lark_table_notes": boss.get("lark_table_notes", ""),
    }


def _ctx_to_workspace(ctx: ChatContext) -> dict:
    return {
        "boss_id": ctx.boss_chat_id,
        "workspace_name": ctx.boss_name,
        "user_role": ctx.sender_type,
        "lark_base_token": ctx.lark_base_token,
        "lark_table_people": ctx.lark_table_people,
        "lark_table_tasks": ctx.lark_table_tasks,
        "lark_table_projects": ctx.lark_table_projects,
        "lark_table_ideas": ctx.lark_table_ideas,
        "lark_table_reminders": ctx.lark_table_reminders,
        "lark_table_notes": getattr(ctx, "lark_table_notes", ""),
    }
