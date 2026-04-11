from datetime import datetime

from src.services import lark
from src.config import Settings


def _date_to_ms(date_str: str) -> int:
    """Convert YYYY-MM-DD to milliseconds timestamp for Lark."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)

_settings: Settings | None = None


def init(settings: Settings):
    global _settings
    _settings = settings


async def create_task(
    name: str,
    assignee: str = "",
    deadline: str = "",
    priority: str = "Trung bình",
    original_message: str = "",
    smart_analysis: str = "",
) -> str:
    fields = {
        "Tên task": name,
        "Khách hàng": assignee,
        "Trạng thái": "Mới",
        "Độ ưu tiên": priority,
    }
    if deadline:
        fields["Deadline"] = _date_to_ms(deadline)
    if original_message:
        fields["Nội dung gốc"] = original_message
    if smart_analysis:
        fields["Phân tích SMART"] = smart_analysis

    record = await lark.create_record(_settings.lark_table_tasks, fields)
    return f"Đã tạo task '{name}' (ID: {record['record_id']})"


async def list_tasks(
    assignee: str = "",
    status: str = "",
    deadline_from: str = "",
    deadline_to: str = "",
) -> str:
    records = await lark.search_records(_settings.lark_table_tasks)

    if assignee:
        records = [r for r in records if assignee.lower() in r.get("Khách hàng", "").lower()]
    if status:
        records = [r for r in records if r.get("Trạng thái") == status]

    if not records:
        return "Không tìm thấy task nào."

    lines = []
    for r in records[:20]:
        line = f"- {r.get('Tên task', '?')} | {r.get('Khách hàng', 'N/A')} | {r.get('Trạng thái', '?')} | DL: {r.get('Deadline', 'N/A')} | {r.get('Độ ưu tiên', 'N/A')}"
        lines.append(line)
    return "\n".join(lines)


async def update_task(
    search_keyword: str,
    status: str = "",
    deadline: str = "",
    priority: str = "",
    assignee: str = "",
) -> str:
    records = await lark.search_records(_settings.lark_table_tasks)
    keyword = search_keyword.lower()

    matched = [r for r in records if keyword in r.get("Tên task", "").lower()]
    if not matched:
        return f"Không tìm thấy task nào chứa '{search_keyword}'."

    fields = {}
    if status:
        fields["Trạng thái"] = status
    if deadline:
        fields["Deadline"] = _date_to_ms(deadline)
    if priority:
        fields["Độ ưu tiên"] = priority
    if assignee:
        fields["Khách hàng"] = assignee

    if not fields:
        return "Không có gì để cập nhật."

    updated = []
    for r in matched:
        await lark.update_record(_settings.lark_table_tasks, r["record_id"], fields)
        updated.append(r.get("Tên task", "?"))

    return f"Đã cập nhật {len(updated)} task: {', '.join(updated)}"


async def search_tasks(query: str) -> str:
    records = await lark.search_records(_settings.lark_table_tasks)
    query_lower = query.lower()

    matched = []
    for r in records:
        searchable = f"{r.get('Tên task', '')} {r.get('Khách hàng', '')} {r.get('Nội dung gốc', '')} {r.get('Ghi chú', '')}".lower()
        if query_lower in searchable:
            matched.append(r)

    if not matched:
        return f"Không tìm thấy task nào liên quan đến '{query}'."

    lines = []
    for r in matched[:10]:
        line = f"- {r.get('Tên task', '?')} | {r.get('Khách hàng', 'N/A')} | {r.get('Trạng thái', '?')} | DL: {r.get('Deadline', 'N/A')}"
        lines.append(line)
    return "\n".join(lines)
