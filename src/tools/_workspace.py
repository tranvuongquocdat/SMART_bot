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
        "current" — only active ctx workspace
        "all"     — all workspaces user belongs to
        [id, ...] — specific boss_ids
    """
    if workspace_ids == "current":
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

    if workspace_ids != "all":
        target_ids = [str(i) for i in workspace_ids]
        memberships = [m for m in memberships if m["boss_chat_id"] in target_ids]

    result = []
    for m in memberships:
        boss = await db.get_boss(m["boss_chat_id"])
        if boss:
            result.append({
                "boss_id": int(boss["chat_id"]),
                "workspace_name": boss.get("company", str(boss["chat_id"])),
                "user_role": m.get("person_type", "member"),
                "lark_base_token": boss["lark_base_token"],
                "lark_table_people": boss.get("lark_table_people", ""),
                "lark_table_tasks": boss.get("lark_table_tasks", ""),
                "lark_table_projects": boss.get("lark_table_projects", ""),
                "lark_table_ideas": boss.get("lark_table_ideas", ""),
                "lark_table_reminders": boss.get("lark_table_reminders", ""),
            })
    return result


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
    }
