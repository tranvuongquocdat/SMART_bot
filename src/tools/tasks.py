import asyncio
from datetime import datetime

from src.context import ChatContext
from src.services import lark, qdrant
from src.services import openai_client


def _date_to_ms(date_str: str) -> int:
    """Convert YYYY-MM-DD to millisecond timestamp for Lark."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)


def _ms_to_date(ms: int) -> str:
    """Convert millisecond timestamp to YYYY-MM-DD string."""
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")


def _format_task(r: dict) -> str:
    deadline = r.get("Deadline")
    dl_str = _ms_to_date(int(deadline)) if isinstance(deadline, (int, float)) else "N/A"
    return (
        f"- {r.get('Tên task', '?')} | Assignee: {r.get('Assignee', 'N/A')} "
        f"| Status: {r.get('Status', '?')} | DL: {dl_str} "
        f"| Priority: {r.get('Priority', 'N/A')}"
    )


async def _embed_and_upsert(ctx: ChatContext, record_id: str, fields: dict):
    """Build text repr of task and upsert to Qdrant."""
    deadline = fields.get("Deadline")
    dl_str = _ms_to_date(int(deadline)) if isinstance(deadline, (int, float)) else ""
    text = " ".join(filter(None, [
        fields.get("Tên task", ""),
        fields.get("Assignee", ""),
        fields.get("Priority", ""),
        fields.get("Status", ""),
        fields.get("Project", ""),
        fields.get("Location", ""),
        fields.get("Tin nhắn gốc", ""),
        dl_str,
    ]))
    await qdrant.ensure_collection(ctx.tasks_collection)
    vector = await openai_client.embed(text)
    await qdrant.upsert_task(ctx.tasks_collection, record_id, text, vector)


async def create_task(
    ctx: ChatContext,
    name: str,
    assignee: str = "",
    deadline: str = "",
    priority: str = "Trung bình",
    project: str = "",
    start_time: str = "",
    location: str = "",
    original_message: str = "",
) -> str:
    fields: dict = {
        "Tên task": name,
        "Priority": priority,
        "Status": "Mới",
        "Giao bởi": ctx.sender_name or ctx.boss_name,
    }
    if assignee:
        fields["Assignee"] = assignee
    if deadline:
        fields["Deadline"] = _date_to_ms(deadline)
    if start_time:
        fields["Start time"] = _date_to_ms(start_time)
    if location:
        fields["Location"] = location
    if project:
        fields["Project"] = project
    if original_message:
        fields["Tin nhắn gốc"] = original_message
    if ctx.is_group:
        fields["Group ID"] = ctx.chat_id

    record = await lark.create_record(ctx.lark_base_token, ctx.lark_table_tasks, fields)
    record_id = record["record_id"]

    asyncio.create_task(_embed_and_upsert(ctx, record_id, fields))

    return f"Đã tạo task '{name}' (ID: {record_id})"


async def list_tasks(
    ctx: ChatContext,
    assignee: str = "",
    status: str = "",
    project: str = "",
) -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)

    if assignee:
        records = [r for r in records if assignee.lower() in r.get("Assignee", "").lower()]
    if status:
        records = [r for r in records if r.get("Status", "").lower() == status.lower()]
    if project:
        records = [r for r in records if project.lower() in r.get("Project", "").lower()]

    if not records:
        return "Không tìm thấy task nào."

    lines = [f"Danh sách task ({len(records)}):"]
    for r in records[:20]:
        lines.append(_format_task(r))
    return "\n".join(lines)


async def update_task(
    ctx: ChatContext,
    search_keyword: str,
    status: str = "",
    deadline: str = "",
    priority: str = "",
    assignee: str = "",
    name: str = "",
) -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)
    keyword = search_keyword.lower()
    matched = [r for r in records if keyword in r.get("Tên task", "").lower()]

    if not matched:
        return f"Không tìm thấy task nào chứa '{search_keyword}'."

    fields: dict = {}
    if status:
        fields["Status"] = status
    if deadline:
        fields["Deadline"] = _date_to_ms(deadline)
    if priority:
        fields["Priority"] = priority
    if assignee:
        fields["Assignee"] = assignee
    if name:
        fields["Tên task"] = name

    if not fields:
        return "Không có gì để cập nhật."

    updated = []
    for r in matched:
        rid = r["record_id"]
        await lark.update_record(ctx.lark_base_token, ctx.lark_table_tasks, rid, fields)
        merged = {**r, **fields}
        asyncio.create_task(_embed_and_upsert(ctx, rid, merged))
        updated.append(r.get("Tên task", "?"))

    return f"Đã cập nhật {len(updated)} task: {', '.join(updated)}"


async def delete_task(ctx: ChatContext, search_keyword: str) -> str:
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)
    keyword = search_keyword.lower()
    matched = [r for r in records if keyword in r.get("Tên task", "").lower()]

    if not matched:
        return f"Không tìm thấy task nào chứa '{search_keyword}'."

    deleted = []
    for r in matched:
        rid = r["record_id"]
        await lark.delete_record(ctx.lark_base_token, ctx.lark_table_tasks, rid)
        asyncio.create_task(qdrant.delete_task(ctx.tasks_collection, rid))
        deleted.append(r.get("Tên task", "?"))

    return f"Đã xóa {len(deleted)} task: {', '.join(deleted)}"


async def search_tasks(ctx: ChatContext, query: str) -> str:
    await qdrant.ensure_collection(ctx.tasks_collection)
    results = await qdrant.search(ctx.tasks_collection, query, chat_id=None, top_n=10)

    record_ids = [r["record_id"] for r in results if r.get("record_id")]
    if not record_ids:
        return f"Không tìm thấy task nào liên quan đến '{query}'."

    all_records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_tasks)
    id_set = set(record_ids)
    matched = [r for r in all_records if r.get("record_id") in id_set]

    if not matched:
        return f"Không tìm thấy task nào liên quan đến '{query}'."

    lines = [f"Kết quả tìm kiếm cho '{query}' ({len(matched)} task):"]
    for r in matched[:10]:
        lines.append(_format_task(r))
    return "\n".join(lines)
