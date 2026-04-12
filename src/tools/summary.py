from datetime import date, datetime

from src.context import ChatContext
from src.services import lark


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


async def get_summary(ctx: ChatContext, summary_type: str = "today", assignee: str = "") -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)

    if not records:
        return "Hiện chưa có task nào."

    if assignee:
        records = [r for r in records if assignee.lower() in r.get("Assignee", "").lower()]

    today_str = date.today().isoformat()
    today_ms = int(datetime.combine(date.today(), datetime.min.time()).timestamp() * 1000)

    active = [r for r in records if r.get("Status") in ("Mới", "Đang làm")]
    done = [r for r in records if r.get("Status") == "Xong"]
    overdue = [
        r for r in active
        if _deadline_ts(r) is not None and _deadline_ts(r) < today_ms
    ]

    lines = []

    if summary_type == "week":
        lines.append("Báo cáo tuần:")
        lines.append(f"  Tổng task: {len(records)}")
        lines.append(f"  Hoàn thành: {len(done)}")
        lines.append(f"  Đang làm: {len(active)}")
        lines.append(f"  Quá hạn: {len(overdue)}")
        if overdue:
            lines.append(f"\nTask quá hạn ({len(overdue)}):")
            for r in overdue[:5]:
                lines.append(f"  - {r.get('Tên task', '?')} | Assignee: {r.get('Assignee', 'N/A')} | DL: {_deadline_str(r)}")
    else:
        header = f"Tóm tắt hôm nay ({today_str})"
        if assignee:
            header += f" - {assignee}"
        lines.append(header + ":")
        lines.append(f"  Tổng: {len(records)} | Đang làm: {len(active)} | Xong: {len(done)} | Quá hạn: {len(overdue)}")
        if active:
            lines.append(f"\nTask cần xử lý ({len(active)}):")
            for r in active[:10]:
                lines.append(f"  - {r.get('Tên task', '?')} | {r.get('Assignee', 'N/A')} | DL: {_deadline_str(r)}")
        if overdue:
            lines.append(f"\nQuá hạn ({len(overdue)}):")
            for r in overdue[:5]:
                lines.append(f"  - {r.get('Tên task', '?')} | DL: {_deadline_str(r)}")
        if not active and not overdue:
            lines.append("Không có task nào cần xử lý.")

    return "\n".join(lines)


async def get_workload(ctx: ChatContext, assignee: str = "") -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)

    active = [r for r in records if r.get("Status") in ("Mới", "Đang làm")]

    if assignee:
        active = [r for r in active if assignee.lower() in r.get("Assignee", "").lower()]

    if not active:
        if assignee:
            return f"{assignee} hiện không có task nào đang hoạt động."
        return "Hiện chưa có task nào đang hoạt động trong hệ thống."

    # Group by assignee
    by_person: dict[str, list[dict]] = {}
    for r in active:
        person = r.get("Assignee", "Chưa giao") or "Chưa giao"
        by_person.setdefault(person, []).append(r)

    lines = []
    if assignee:
        lines.append(f"Workload của {assignee}:")
    else:
        lines.append(f"Workload toàn nhóm ({len(active)} task đang hoạt động):")

    for person, tasks in sorted(by_person.items(), key=lambda x: -len(x[1])):
        lines.append(f"\n  {person}: {len(tasks)} task")
        for t in tasks[:5]:
            dl = _deadline_str(t)
            lines.append(f"    - {t.get('Tên task', '?')} | DL: {dl} | {t.get('Priority', 'N/A')}")
        if len(tasks) > 5:
            lines.append(f"    ... và {len(tasks) - 5} task khác")

    return "\n".join(lines)
