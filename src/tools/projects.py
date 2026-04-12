"""
Project CRUD tools.
All functions take a ChatContext as first argument.
"""
from datetime import datetime

from src.context import ChatContext
from src.services import lark


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
) -> str:
    fields: dict = {
        "Tên dự án": name,
        "Trạng thái": "Planning",
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


async def get_project(ctx: ChatContext, search_name: str) -> str:
    records = await _find_project(ctx, search_name)
    if not records:
        return f"Không tìm thấy dự án '{search_name}'."

    lines = []
    for proj in records:
        lines.append(_fmt_project(proj))

        # List related tasks
        all_tasks = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)
        proj_name = proj.get("Tên dự án", "")
        related = [
            t for t in all_tasks
            if proj_name.lower() in str(t.get("Project", "")).lower()
        ]
        if related:
            lines.append(f"  Tasks ({len(related)}):")
            for t in related:
                task_name = t.get("Tên task", "?")
                status = t.get("Status", "")
                assignee = t.get("Assignee", "")
                lines.append(f"    - {task_name} | {status} | {assignee}")
        else:
            lines.append("  Tasks: (chưa có)")

    return "\n".join(lines)


async def list_projects(ctx: ChatContext, status: str = "") -> str:
    all_records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_projects)

    filtered = all_records
    if status:
        filtered = [r for r in filtered if status.lower() in str(r.get("Trạng thái", "")).lower()]

    if not filtered:
        return "Không có dự án nào."

    lines = [f"Danh sách dự án ({len(filtered)}):"]
    for r in filtered:
        lines.append(f"- {_fmt_project(r)}")
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
        updates["Trạng thái"] = status

    if not updates:
        return "Không có trường nào được cập nhật."

    updated = 0
    for r in records:
        await lark.update_record(ctx.lark_base_token, ctx.lark_table_projects, r["record_id"], updates)
        updated += 1

    return f"Đã cập nhật {updated} dự án tên '{search_name}'."


async def delete_project(ctx: ChatContext, search_name: str) -> str:
    records = await _find_project(ctx, search_name)
    if not records:
        return f"Không tìm thấy dự án '{search_name}'."

    deleted = 0
    for r in records:
        await lark.delete_record(ctx.lark_base_token, ctx.lark_table_projects, r["record_id"])
        deleted += 1

    return f"Đã xóa {deleted} dự án tên '{search_name}'."
