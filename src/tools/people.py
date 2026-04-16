"""
People CRUD tools + effort check.
All functions take a ChatContext as first argument.
"""
from datetime import datetime

from src import db
from src.context import ChatContext
from src.services import lark


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _date_to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)


def _fmt_person(r: dict) -> str:
    parts = [f"Tên: {r.get('Tên', '')}"]
    if r.get("Tên gọi"):
        parts.append(f"Tên gọi: {r['Tên gọi']}")
    if r.get("Type"):
        parts.append(f"Type: {r['Type']}")
    if r.get("Nhóm"):
        parts.append(f"Nhóm: {r['Nhóm']}")
    if r.get("Vai trò"):
        parts.append(f"Vai trò: {r['Vai trò']}")
    if r.get("Kỹ năng"):
        parts.append(f"Kỹ năng: {r['Kỹ năng']}")
    if r.get("SĐT"):
        parts.append(f"SĐT: {r['SĐT']}")
    if r.get("Username"):
        parts.append(f"Username: {r['Username']}")
    if r.get("Ghi chú"):
        parts.append(f"Ghi chú: {r['Ghi chú']}")
    return " | ".join(parts)


async def _find_person(ctx: ChatContext, search_name: str) -> list[dict]:
    """Return all people records whose Tên or Tên gọi contains search_name."""
    all_records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    search_lower = search_name.lower()
    return [
        r for r in all_records
        if search_lower in str(r.get("Tên", "")).lower()
        or search_lower in str(r.get("Tên gọi", "")).lower()
    ]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def add_people(
    ctx: ChatContext,
    name: str,
    chat_id: int = 0,
    username: str = "",
    group: str = "",
    person_type: str = "member",
    role_desc: str = "",
    skills: str = "",
    note: str = "",
) -> str:
    fields: dict = {
        "Tên": name,
        "Type": person_type,
    }
    if chat_id:
        fields["Chat ID"] = chat_id
    if username:
        fields["Username"] = username
    if group:
        fields["Nhóm"] = group
    if role_desc:
        fields["Vai trò"] = role_desc
    if skills:
        fields["Kỹ năng"] = skills
    if note:
        fields["Ghi chú"] = note

    await lark.create_record(ctx.lark_base_token, ctx.lark_table_people, fields)

    if chat_id and ctx.boss_chat_id:
        await db.add_person(
            chat_id=chat_id,
            boss_chat_id=ctx.boss_chat_id,
            person_type=person_type,
            name=name,
        )

    return f"Đã thêm người: {name} (type: {person_type})"


async def get_people(ctx: ChatContext, search_name: str) -> str:
    records = await _find_person(ctx, search_name)
    if not records:
        return f"Không tìm thấy ai tên '{search_name}'."
    lines = [f"Tìm thấy {len(records)} người:"]
    for r in records:
        lines.append(f"- {_fmt_person(r)}")
    return "\n".join(lines)


async def list_people(ctx: ChatContext, group: str = "", person_type: str = "") -> str:
    all_records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)

    filtered = all_records
    if group:
        filtered = [r for r in filtered if group.lower() in str(r.get("Nhóm", "")).lower()]
    if person_type:
        filtered = [r for r in filtered if person_type.lower() in str(r.get("Type", "")).lower()]

    if not filtered:
        return "Không có ai trong danh sách."

    lines = [f"Danh sách ({len(filtered)} người):"]
    for r in filtered:
        lines.append(f"- {_fmt_person(r)}")
    return "\n".join(lines)


async def update_people(
    ctx: ChatContext,
    search_name: str,
    name: str = "",
    nickname: str = "",
    group: str = "",
    role_desc: str = "",
    skills: str = "",
    note: str = "",
    phone: str = "",
    username: str = "",
    person_type: str = "",
) -> str:
    records = await _find_person(ctx, search_name)
    if not records:
        return f"Không tìm thấy ai tên '{search_name}'."

    field_map = {
        "name": "Tên",
        "nickname": "Tên gọi",
        "group": "Nhóm",
        "role_desc": "Vai trò",
        "skills": "Kỹ năng",
        "note": "Ghi chú",
        "phone": "SĐT",
        "username": "Username",
        "person_type": "Type",
    }
    local_vars = locals()
    updates: dict = {}
    for param, field in field_map.items():
        val = local_vars.get(param, "")
        if val:
            updates[field] = val

    if not updates:
        return "Không có trường nào được cập nhật."

    updated = 0
    for r in records:
        await lark.update_record(ctx.lark_base_token, ctx.lark_table_people, r["record_id"], updates)
        updated += 1

    return f"Đã cập nhật {updated} người tên '{search_name}'."


async def delete_people(ctx: ChatContext, search_name: str) -> str:
    records = await _find_person(ctx, search_name)
    if not records:
        return f"Không tìm thấy ai tên '{search_name}'."

    deleted = 0
    for r in records:
        # Remove from Lark
        await lark.delete_record(ctx.lark_base_token, ctx.lark_table_people, r["record_id"])

        # Remove from SQLite if Chat ID present
        chat_id_val = r.get("Chat ID")
        if chat_id_val:
            try:
                await db.delete_person(int(chat_id_val))
            except Exception:
                pass
        deleted += 1

    return f"Đã xóa {deleted} người tên '{search_name}'."


# ---------------------------------------------------------------------------
# Cross-workspace search
# ---------------------------------------------------------------------------

async def search_person(ctx: ChatContext, search_name: str, workspace_ids: str = "current") -> str:
    from src.tools._workspace import resolve_workspaces

    workspaces = await resolve_workspaces(ctx, workspace_ids)
    all_results = []

    for ws in workspaces:
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_people"])
            matches = [
                r for r in records
                if search_name.lower() in str(r.get("Tên", "")).lower()
                or search_name.lower() in str(r.get("Tên gọi", "")).lower()
            ]
            for r in matches:
                all_results.append({
                    "workspace": ws["workspace_name"],
                    "name": r.get("Tên", ""),
                    "nickname": r.get("Tên gọi", ""),
                    "type": r.get("Type", ""),
                    "role": r.get("Vai trò", ""),
                    "group": r.get("Nhóm", ""),
                    "record_id": r.get("record_id", ""),
                })
        except Exception:
            continue

    if not all_results:
        return f"No one found matching '{search_name}'."

    lines = []
    for r in all_results:
        label = f"[{r['workspace']}] " if workspace_ids != "current" else ""
        name = f"{r['name']} ({r['nickname']})" if r.get("nickname") else r["name"]
        parts = [label + name, r["type"], r["role"], r["group"]]
        lines.append(" | ".join(p for p in parts if p))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Effort / workload check
# ---------------------------------------------------------------------------

async def check_effort(ctx: ChatContext, assignee: str, deadline: str = "", workspace_ids: str = "current") -> str:
    from src.tools._workspace import resolve_workspaces

    workspaces = await resolve_workspaces(ctx, workspace_ids)
    all_tasks = []

    for ws in workspaces:
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_tasks"])
            tasks = [
                t for t in records
                if assignee.lower() in str(t.get("Assignee", "")).lower()
                and str(t.get("Status", "")).lower() not in ("done", "hoàn thành", "cancelled")
            ]
            for t in tasks:
                t["_workspace"] = ws["workspace_name"]
            all_tasks.extend(tasks)
        except Exception:
            continue

    if not all_tasks:
        return f"{assignee} hiện không có task nào đang mở."

    lines = [f"{assignee} đang có {len(all_tasks)} task:"]
    conflicts = []

    deadline_ms = _date_to_ms(deadline) if deadline else None

    for t in all_tasks:
        task_name = t.get("Tên task", "?")
        task_deadline = t.get("Deadline")
        status = t.get("Status", "")
        ws_label = f"[{t['_workspace']}] " if workspace_ids != "current" else ""
        line = f"  - {ws_label}{task_name} | Status: {status}"
        if task_deadline:
            try:
                task_dt = datetime.fromtimestamp(int(task_deadline) / 1000)
                line += f" | Deadline: {task_dt.strftime('%Y-%m-%d')}"
                if deadline_ms and int(task_deadline) <= deadline_ms:
                    conflicts.append(task_name)
            except (ValueError, TypeError):
                pass
        lines.append(line)

    if conflicts:
        lines.append(f"\nCảnh báo: {len(conflicts)} task trùng deadline với '{deadline}': {', '.join(conflicts)}")

    return "\n".join(lines)
