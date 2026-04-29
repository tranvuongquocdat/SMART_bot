import json

from src.context import ChatContext
from src.tools import (
    tasks,
    people,
    projects,
    ideas,
    note,
    memory,
    summary,
    reminder,
    review_config,
    web_search,
    join,
    reset,
)
from src.tools import workspace as workspace_tools
from src.tools import group as group_tools
from src.tools import communication
from src.tools import search as search_tools


# Re-export from agent_pkg so legacy callers keep working until 4b-3.
from src.agent_pkg.tool_definitions import TOOL_DEFINITIONS  # noqa: F401




# ---------------------------------------------------------------------------
# Tool router
# ---------------------------------------------------------------------------

async def execute_tool(name: str, arguments: str | dict, ctx: ChatContext) -> str:
    try:
        args_dict = json.loads(arguments) if isinstance(arguments, str) else arguments
        return await _dispatch_tool(name, args_dict, ctx)
    except Exception as e:
        err_type = type(e).__name__
        msg = str(e)
        if any(kw in msg.lower() for kw in ("lark", "base_token", "table", "record")):
            return (
                f"[TOOL_ERROR:lark] {name} — Lark không phản hồi hoặc cấu hình sai: {msg}. "
                f"Thử lại hoặc báo người dùng."
            )
        if any(kw in msg.lower() for kw in ("not found", "không tìm thấy", "no such")):
            return (
                f"[TOOL_ERROR:not_found] {name} — {msg}. "
                f"Hãy hỏi lại người dùng tên chính xác."
            )
        return f"[TOOL_ERROR:unknown] {name} thất bại ({err_type}): {msg}"


async def _dispatch_tool(name: str, args: dict, ctx: ChatContext) -> str:
    match name:
        # Task tools
        case "create_task":
            return await tasks.create_task(ctx, **args)
        case "list_tasks":
            return await tasks.list_tasks(ctx, **args)
        case "update_task":
            return await tasks.update_task(ctx, **args)
        case "delete_task":
            return await tasks.delete_task(ctx, **args)
        case "search_tasks":
            return await tasks.search_tasks(ctx, **args)

        # People tools
        case "add_people":
            return await people.add_people(ctx, **args)
        case "get_people" | "get_person":
            return await people.get_person(ctx, **args)
        case "list_people":
            return await people.list_people(ctx, **args)
        case "update_people":
            return await people.update_people(ctx, **args)
        case "delete_people":
            return await people.delete_people(ctx, **args)
        case "check_effort":
            return await people.check_effort(ctx, **args)
        case "check_team_engagement":
            return await people.check_team_engagement(ctx, **args)

        # Project tools
        case "create_project":
            return await projects.create_project(ctx, **args)
        case "get_project":
            return await projects.get_project(ctx, **args)
        case "list_projects":
            return await projects.list_projects(ctx, **args)
        case "update_project":
            return await projects.update_project(ctx, **args)
        case "delete_project":
            return await projects.delete_project(ctx, **args)

        # Note tools
        case "update_note":
            return await note.update_note(ctx, **args)
        case "get_note":
            return await note.get_note(ctx, **args)

        # Search tools
        case "search_history":
            return await search_tools.search_history(ctx, **args)
        case "search_notes":
            return await search_tools.search_notes(ctx, **args)

        # Summary tools
        case "get_summary":
            return await summary.get_summary(ctx, **args)
        case "get_workload":
            return await summary.get_workload(ctx, **args)
        case "get_project_report":
            return await summary.get_project_report(ctx, **args)

        # Idea tools
        case "create_idea":
            return await ideas.create_idea(ctx, **args)

        # Reminder tools
        case "create_reminder":
            return await reminder.create_reminder(ctx, **args)
        case "list_reminders":
            return await reminder.list_reminders(ctx, **args)
        case "update_reminder":
            return await reminder.update_reminder(ctx, **args)
        case "delete_reminder":
            return await reminder.delete_reminder(ctx, **args)

        # Review schedule config tools
        case "add_review_schedule":
            return await review_config.add_review_schedule(ctx, **args)
        case "list_review_schedules":
            return await review_config.list_review_schedules(ctx)
        case "toggle_review":
            return await review_config.toggle_review(ctx, **args)
        case "delete_review_schedule":
            return await review_config.delete_review_schedule(ctx, **args)

        # Web search tools
        case "web_search":
            return await web_search.web_search(**args)

        # Advisor escalation
        case "escalate_to_advisor":
            return "__ESCALATE__"

        # Note — append
        case "append_note":
            return await note.append_note(ctx, **args)

        # Approval tools
        case "list_pending_approvals":
            return await memory.list_pending_approvals(ctx)
        case "approve_task_change":
            return await tasks.approve_task_change(ctx, **args)
        case "reject_task_change":
            return await tasks.reject_task_change(ctx, **args)

        # Join flow tools
        case "list_available_workspaces":
            return await join.list_available_workspaces(ctx)
        case "request_join":
            return await join.request_join(ctx, **args)
        case "approve_join":
            return await join.approve_join(ctx, **args)
        case "reject_join":
            return await join.reject_join(ctx, **args)

        # Reset tools
        case "initiate_reset":
            return await reset.initiate_reset(ctx)
        case "confirm_reset_step1":
            return await reset.confirm_reset_step1(ctx, **args)
        case "execute_reset":
            return await reset.execute_reset(ctx, **args)

        # Group tools
        case "manage_group":
            return await group_tools.manage_group(ctx, **args)

        # Communication tools
        case "send_dm":
            return await communication.send_dm(ctx, **args)
        case "broadcast":
            return await communication.broadcast(ctx, **args)
        case "get_communication_log":
            return await communication.get_communication_log(ctx, **args)
        case "resolve_person":
            return await communication.resolve_person(ctx, **args)
        case "link_contact_to_person":
            return await communication.link_contact_to_person(ctx, **args)
        case "list_unlinked_contacts":
            return await communication.list_unlinked_contacts(ctx, **args)
        case "get_group_admins":
            return await communication.get_group_admins(ctx, **args)

        # Group-context tools
        case "summarize_group_conversation":
            return await group_tools.summarize_group_conversation(ctx, **args)
        case "update_group_note":
            return await group_tools.update_group_note(ctx, **args)
        case "broadcast_to_group":
            return await group_tools.broadcast_to_group(ctx, **args)

        # Workspace & language tools
        case "set_language":
            return await workspace_tools.set_language(ctx, **args)
        case "switch_workspace":
            return await workspace_tools.switch_workspace(ctx, **args)

        case _:
            return f"Tool '{name}' không tồn tại."
