from datetime import date, timedelta

from src.services import lark
from src.config import Settings

_settings: Settings | None = None


def init(settings: Settings):
    global _settings
    _settings = settings


async def get_summary(summary_type: str = "today") -> str:
    records = await lark.search_records(_settings.lark_table_tasks)

    if not records:
        return "Hiện chưa có task nào."

    today = date.today().isoformat()

    active = [r for r in records if r.get("Trạng thái") in ("Mới", "Đang làm")]
    done = [r for r in records if r.get("Trạng thái") == "Xong"]
    overdue = [r for r in records if r.get("Trạng thái") in ("Mới", "Đang làm") and r.get("Deadline", "9999") < today]

    lines = []

    if summary_type == "week":
        lines.append(f"Báo cáo tuần:")
        lines.append(f"  Tổng task: {len(records)}")
        lines.append(f"  Hoàn thành: {len(done)}")
        lines.append(f"  Đang làm: {len(active)}")
        lines.append(f"  Quá hạn: {len(overdue)}")
    else:
        lines.append(f"Tóm tắt hôm nay ({today}):")
        if active:
            lines.append(f"\nTask cần xử lý ({len(active)}):")
            for r in active[:10]:
                lines.append(f"  - {r.get('Tên task', '?')} | {r.get('Khách hàng', 'N/A')} | DL: {r.get('Deadline', 'N/A')}")
        if overdue:
            lines.append(f"\nQuá hạn ({len(overdue)}):")
            for r in overdue[:5]:
                lines.append(f"  - {r.get('Tên task', '?')} | DL: {r.get('Deadline', 'N/A')}")
        if not active and not overdue:
            lines.append("Không có task nào cần xử lý.")

    return "\n".join(lines)
