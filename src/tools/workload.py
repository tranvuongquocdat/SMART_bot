from src.services import lark
from src.config import Settings

_settings: Settings | None = None


def init(settings: Settings):
    global _settings
    _settings = settings


async def get_workload(assignee: str = "") -> str:
    records = await lark.search_records(_settings.lark_table_tasks)

    if assignee:
        records = [r for r in records if assignee.lower() in r.get("Khách hàng", "").lower()]

    if not records:
        if assignee:
            return f"{assignee} hiện không có task nào."
        return "Hiện chưa có task nào trong hệ thống."

    by_status = {}
    for r in records:
        s = r.get("Trạng thái", "Không rõ")
        by_status.setdefault(s, []).append(r)

    lines = []
    if assignee:
        lines.append(f"Workload của {assignee}: {len(records)} task")
    else:
        lines.append(f"Tổng: {len(records)} task")

    for status, tasks in by_status.items():
        lines.append(f"  {status}: {len(tasks)}")
        for t in tasks[:5]:
            lines.append(f"    - {t.get('Tên task', '?')} | DL: {t.get('Deadline', 'N/A')}")

    return "\n".join(lines)
