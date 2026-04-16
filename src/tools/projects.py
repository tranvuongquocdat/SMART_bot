"""
Project CRUD tools.
All functions take a ChatContext as first argument.
"""
from datetime import datetime

from src.context import ChatContext
from src.services import lark

# Canonical enum values — must match Lark field options exactly
PROJECT_STATUS_VALUES = ("Chưa bắt đầu", "Đang thực hiện", "Hoàn thành", "Tạm dừng", "Huỷ")


def _validate_project_status(status: str) -> str:
    for v in PROJECT_STATUS_VALUES:
        if status.lower() == v.lower():
            return v
    raise ValueError(
        f"Status '{status}' không hợp lệ. Dùng: {', '.join(PROJECT_STATUS_VALUES)}"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _date_to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)


def _fmt_project(r: dict) -> str:
    parts = [f"Tên: {r.get('Tên dự án', '')}"]
    if r.get("Trạng thái"):
        parts.append(f"Trạng thái: {r['Trạng thái']}")
    if r.get("Người phụ trách"):
        parts.append(f"Phụ trách: {r['Người phụ trách']}")
    if r.get("Thành viên"):
        parts.append(f"Thành viên: {r['Thành viên']}")
    if r.get("Deadline"):
        try:
            dt = datetime.fromtimestamp(int(r["Deadline"]) / 1000)
            parts.append(f"Deadline: {dt.strftime('%Y-%m-%d')}")
        except (ValueError, TypeError):
            pass
    if r.get("Mô tả"):
        parts.append(f"Mô tả: {r['Mô tả']}")
    return " | ".join(parts)


async def _find_project(ctx: ChatContext, search_name: str) -> list[dict]:
    all_records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_projects)
    search_lower = search_name.lower()
    return [
        r for r in all_records
        if search_lower in str(r.get("Tên dự án", "")).lower()
    ]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def create_project(
    ctx: ChatContext,
    name: str,
    description: str = "",
    lead: str = "",
    members: str = "",
    deadline: str = "",
    workspace_ids: str = "current",
) -> str:
    fields: dict = {
        "Tên dự án": name,
        "Trạng thái": "Chưa bắt đầu",
    }
    if description:
        fields["Mô tả"] = description
    if lead:
        fields["Người phụ trách"] = lead
    if members:
        fields["Thành viên"] = members
    if deadline:
        fields["Deadline"] = _date_to_ms(deadline)

    await lark.create_record(ctx.lark_base_token, ctx.lark_table_projects, fields)
    return f"Đã tạo dự án: {name}"


async def get_project(
    ctx: ChatContext,
    search_name: str,
    workspace_ids: str = "current",
) -> str:
    """
    Fat return: project info + tasks by status + progress %.
    workspace_ids: "current" | "all" | specific boss_id
    """
    from src.tools._workspace import resolve_workspaces
    workspaces = await resolve_workspaces(ctx, workspace_ids)
    lines = []

    for ws in workspaces:
        if not ws.get("lark_table_projects"):
            continue
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_projects"])
        except Exception:
            continue
        matches = [r for r in records if search_name.lower() in str(r.get("Tên dự án", "")).lower()]
        for proj in matches:
            ws_label = f" [{ws['workspace_name']}]" if workspace_ids != "current" else ""
            lines.append(f"=== {proj.get('Tên dự án', '?')}{ws_label} ===")
            lines.append(_fmt_project(proj))

            # Tasks with progress %
            try:
                all_tasks = await lark.search_records(ws["lark_base_token"], ws["lark_table_tasks"])
                proj_name = proj.get("Tên dự án", "")
                related = [t for t in all_tasks if proj_name.lower() in str(t.get("Project", "")).lower()]
                total = len(related)
                done = sum(1 for t in related if t.get("Status") in ("Hoàn thành", "Done"))
                progress = f"{done}/{total} ({int(done / total * 100)}%)" if total else "0/0"
                lines.append(f"Tiến độ: {progress} task hoàn thành")
                for t in related:
                    lines.append(
                        f"  - {t.get('Tên task', '?')} | {t.get('Assignee', '?')} | {t.get('Status', '?')}"
                    )
            except Exception:
                lines.append("Tasks: (không tải được)")

    if not lines:
        return f"Không tìm thấy dự án '{search_name}'."
    return "\n".join(lines)


async def list_projects(
    ctx: ChatContext,
    status: str = "",
    workspace_ids: str = "current",
) -> str:
    from src.tools._workspace import resolve_workspaces
    workspaces = await resolve_workspaces(ctx, workspace_ids)
    all_results = []

    for ws in workspaces:
        if not ws.get("lark_table_projects"):
            continue
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_projects"])
        except Exception:
            continue
        for r in records:
            if status and status.lower() not in str(r.get("Trạng thái", "")).lower():
                continue
            r["_workspace"] = ws["workspace_name"]
            all_results.append(r)

    if not all_results:
        return "Không có dự án nào."

    lines = [f"Danh sách dự án ({len(all_results)}):"]
    for r in all_results:
        ws_label = f"[{r['_workspace']}] " if workspace_ids != "current" else ""
        lines.append(f"- {ws_label}{_fmt_project(r)}")
    return "\n".join(lines)


async def update_project(
    ctx: ChatContext,
    search_name: str,
    name: str = "",
    description: str = "",
    lead: str = "",
    members: str = "",
    deadline: str = "",
    status: str = "",
    workspace_ids: str = "current",
) -> str:
    records = await _find_project(ctx, search_name)
    if not records:
        return f"Không tìm thấy dự án '{search_name}'."

    updates: dict = {}
    if name:
        updates["Tên dự án"] = name
    if description:
        updates["Mô tả"] = description
    if lead:
        updates["Người phụ trách"] = lead
    if members:
        updates["Thành viên"] = members
    if deadline:
        updates["Deadline"] = _date_to_ms(deadline)
    if status:
        updates["Trạng thái"] = _validate_project_status(status)

    if not updates:
        return "Không có trường nào được cập nhật."

    updated = 0
    for r in records:
        await lark.update_record(ctx.lark_base_token, ctx.lark_table_projects, r["record_id"], updates)
        updated += 1

    return f"Đã cập nhật {updated} dự án tên '{search_name}'."


async def delete_project(
    ctx: ChatContext,
    search_name: str,
    workspace_ids: str = "current",
) -> str:
    records = await _find_project(ctx, search_name)
    if not records:
        return f"Không tìm thấy dự án '{search_name}'."

    deleted = 0
    for r in records:
        await lark.delete_record(ctx.lark_base_token, ctx.lark_table_projects, r["record_id"])
        deleted += 1

    return f"Đã xóa {deleted} dự án tên '{search_name}'."
