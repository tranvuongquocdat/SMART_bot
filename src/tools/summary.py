from datetime import date, datetime

from src.context import ChatContext
from src.services import lark
from src.tools._workspace import resolve_workspaces


def _deadline_ts(record: dict) -> int | None:
    dl = record.get("Deadline")
    if isinstance(dl, (int, float)):
        return int(dl)
    return None


def _deadline_str(record: dict) -> str:
    dl = record.get("Deadline")
    if isinstance(dl, (int, float)):
        return datetime.fromtimestamp(dl / 1000).strftime("%Y-%m-%d")
    return "N/A"


async def get_summary(
    ctx: ChatContext,
    summary_type: str = "today",
    assignee: str = "",
    workspace_ids: str = "current",
) -> str:
    # Multi-workspace path
    if workspace_ids != "current":
        workspaces = await resolve_workspaces(ctx, workspace_ids)
        all_records = []
        for ws in workspaces:
            if not ws.get("lark_table_tasks"):
                continue
            try:
                recs = await lark.search_records(ws["lark_base_token"], ws["lark_table_tasks"])
                for r in recs:
                    r["_workspace"] = ws["workspace_name"]
                all_records.extend(recs)
            except Exception:
                continue
        records = all_records
    else:
        records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)

    if not records:
        return "Hiện chưa có task nào."

    if assignee:
        records = [r for r in records if assignee.lower() in r.get("Assignee", "").lower()]

    today_str = date.today().isoformat()
    today_ms = int(datetime.combine(date.today(), datetime.min.time()).timestamp() * 1000)

    active = [r for r in records if r.get("Status") in ("Mới", "Đang làm")]
    done = [r for r in records if r.get("Status") in ("Hoàn thành", "Huỷ")]
    overdue = [
        r for r in active
        if _deadline_ts(r) is not None and _deadline_ts(r) < today_ms
    ]

    def _task_line(r: dict) -> str:
        ws = r.get("_workspace", "")
        tag = f"[{ws}] " if ws and workspace_ids != "current" else ""
        return f"  {tag}- {r.get('Tên task', '?')} | {r.get('Assignee', 'N/A')} | DL: {_deadline_str(r)}"

    lines = []

    if summary_type == "week":
        lines.append("Báo cáo tuần:")
        lines.append(f"  Tổng task: {len(records)}")
        lines.append(f"  Hoàn thành/Huỷ: {len(done)}")
        lines.append(f"  Đang làm: {len(active)}")
        lines.append(f"  Quá hạn: {len(overdue)}")
        if overdue:
            lines.append(f"\nTask quá hạn ({len(overdue)}):")
            for r in overdue[:5]:
                lines.append(_task_line(r))
    else:
        header = f"Tóm tắt hôm nay ({today_str})"
        if assignee:
            header += f" - {assignee}"
        lines.append(header + ":")
        lines.append(f"  Tổng: {len(records)} | Đang làm: {len(active)} | Xong: {len(done)} | Quá hạn: {len(overdue)}")
        if active:
            lines.append(f"\nTask cần xử lý ({len(active)}):")
            for r in active[:10]:
                lines.append(_task_line(r))
        if overdue:
            lines.append(f"\nQuá hạn ({len(overdue)}):")
            for r in overdue[:5]:
                lines.append(_task_line(r))
        if not active and not overdue:
            lines.append("Không có task nào cần xử lý.")

    return "\n".join(lines)


async def get_workload(
    ctx: ChatContext,
    assignee: str = "",
    workspace_ids: str = "all",
) -> str:
    """
    Effort overview. workspace_ids defaults to "all" for accurate total load.
    Returns combined task count across all workspaces.
    """
    from src.tools._workspace import resolve_workspaces
    workspaces = await resolve_workspaces(ctx, workspace_ids)
    all_active = []

    for ws in workspaces:
        if not ws.get("lark_table_tasks"):
            continue
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_tasks"])
            for r in records:
                if r.get("Status") not in ("Mới", "Đang làm"):
                    continue
                if assignee and assignee.lower() not in r.get("Assignee", "").lower():
                    continue
                r["_workspace"] = ws["workspace_name"]
                all_active.append(r)
        except Exception:
            continue

    if not all_active:
        if assignee:
            return f"{assignee} hiện không có task nào đang hoạt động."
        return "Hiện chưa có task nào đang hoạt động trong hệ thống."

    by_person: dict[str, list[dict]] = {}
    for r in all_active:
        person = r.get("Assignee", "Chưa giao") or "Chưa giao"
        by_person.setdefault(person, []).append(r)

    lines = []
    if assignee:
        lines.append(f"Workload của {assignee} ({len(all_active)} task):")
    else:
        lines.append(f"Workload toàn nhóm ({len(all_active)} task đang hoạt động):")

    for person, tasks in sorted(by_person.items(), key=lambda x: -len(x[1])):
        overload = " ⚠️OVERLOAD" if len(tasks) >= 5 else ""
        lines.append(f"\n  {person}: {len(tasks)} task{overload}")
        for t in tasks[:5]:
            dl = _deadline_str(t)
            ws_label = f" [{t['_workspace']}]" if workspace_ids != "current" else ""
            lines.append(f"    - {t.get('Tên task', '?')} | DL: {dl} | {t.get('Priority', 'N/A')}{ws_label}")
        if len(tasks) > 5:
            lines.append(f"    ... và {len(tasks) - 5} task khác")

    return "\n".join(lines)


async def get_project_report(
    ctx: ChatContext,
    project: str,
    workspace_ids: str = "current",
) -> str:
    """
    LLM-generated comprehensive project status report.
    Covers: progress %, tasks by status, who's blocking, upcoming deadlines.
    """
    from src.tools._workspace import resolve_workspaces
    from src.services import openai_client as _oai

    workspaces = await resolve_workspaces(ctx, workspace_ids)
    tasks_text = ""

    for ws in workspaces:
        if not ws.get("lark_table_tasks"):
            continue
        try:
            all_tasks = await lark.search_records(ws["lark_base_token"], ws["lark_table_tasks"])
            related = [t for t in all_tasks if project.lower() in str(t.get("Project", "")).lower()]
            for t in related:
                tasks_text += (
                    f"- {t.get('Tên task', '?')} | {t.get('Assignee', '?')} "
                    f"| {t.get('Status', '?')} | DL: {_deadline_str(t)}\n"
                )
        except Exception:
            continue

    if not tasks_text:
        return f"Không tìm thấy task nào cho dự án '{project}'."

    response, _ = await _oai.chat_with_tools(
        [
            {"role": "system", "content": (
                f"Tạo báo cáo tổng quan dự án '{project}' theo:\n"
                "1. Tiến độ tổng thể (% hoàn thành)\n"
                "2. Tasks theo trạng thái\n"
                "3. Ai đang chặn tiến độ (task quá hạn hoặc chưa bắt đầu)\n"
                "4. Deadline quan trọng sắp tới\n"
                "Ngắn gọn, dạng bullet."
            )},
            {"role": "user", "content": f"Danh sách tasks:\n{tasks_text}"},
        ],
        [],
    )
    return response.content or "Không thể tạo báo cáo."
