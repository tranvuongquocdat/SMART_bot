import asyncio
import json
from datetime import datetime

from src import db as db_mod
from src.context import ChatContext
from src.services import lark, qdrant, telegram
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


async def _find_assignee_chat_id(ctx: ChatContext, assignee_name: str) -> tuple[str | None, bool]:
    """Search People table for assignee. Returns (chat_id_or_None, found_in_people)."""
    if not assignee_name:
        return None, False
    records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
    name_lower = assignee_name.lower()
    for r in records:
        full = (r.get("Tên", "") + " " + r.get("Tên gọi", "")).lower()
        if name_lower in full:
            raw = r.get("Chat ID")
            return (str(int(raw)) if raw else None, True)
    return None, False


async def _notify_assignee_task(
    assignee_chat_id: str, task_name: str, deadline: str,
    assigner_name: str, boss_chat_id: int = 0,
):
    msg = (
        f"📋 Bạn vừa được giao task mới!\n\n"
        f"Task: {task_name}\n"
        f"Deadline: {deadline or 'Chưa xác định'}\n"
        f"Giao bởi: {assigner_name}\n\n"
        f"Reply để xác nhận, hỏi thêm thông tin, hoặc đề xuất thay đổi nhé."
    )
    await telegram.send(int(assignee_chat_id), msg)
    if boss_chat_id:
        await db_mod.log_outbound_dm(
            boss_chat_id=boss_chat_id,
            to_chat_id=int(assignee_chat_id),
            to_name="",
            content=msg,
            trigger_type="task_assigned",
        )


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

    # Validate assignee & notify
    warning = ""
    assignee_chat_id = None
    if assignee:
        assignee_chat_id, found = await _find_assignee_chat_id(ctx, assignee)
        if not found:
            warning = (f"\n\n⚠️ Không tìm thấy '{assignee}' trong danh sách nhân sự — "
                       f"task vẫn được tạo nhưng không tự động thông báo.")
        elif not assignee_chat_id:
            warning = (f"\n\n⚠️ '{assignee}' có trong danh sách nhưng chưa có tài khoản liên kết — "
                       f"sẽ không tự động nhận thông báo.")

    # Track notification in DB
    await db_mod.upsert_task_notification(
        db_mod._db, record_id, str(ctx.boss_chat_id), assignee_chat_id
    )

    # Notify assignee async
    if assignee_chat_id:
        asyncio.create_task(_notify_assignee_task(
            assignee_chat_id, name, deadline,
            ctx.sender_name or ctx.boss_name, ctx.boss_chat_id,
        ))

    return f"Đã tạo task '{name}' (ID: {record_id}).{warning}"


async def list_tasks(
    ctx: ChatContext,
    assignee: str = "",
    status: str = "",
    project: str = "",
    workspace_ids: str = "current",
) -> str:
    from src.tools._workspace import resolve_workspaces

    workspaces = await resolve_workspaces(ctx, workspace_ids)
    all_tasks = []

    for ws in workspaces:
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_tasks"])
            for r in records:
                if assignee and assignee.lower() not in r.get("Assignee", "").lower():
                    continue
                if status and r.get("Status", "").lower() != status.lower():
                    continue
                if project and project.lower() not in r.get("Project", "").lower():
                    continue
                r["_workspace"] = ws["workspace_name"]
                all_tasks.append(r)
        except Exception:
            continue

    if not all_tasks:
        return "Không tìm thấy task nào."

    lines = [f"Danh sách task ({len(all_tasks)}):"]
    for r in all_tasks[:20]:
        ws_label = f"[{r['_workspace']}] " if workspace_ids != "current" else ""
        lines.append(ws_label + _format_task(r))
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

    # Non-boss: create pending approval request
    if ctx.sender_type in ("member", "partner"):
        record = matched[0]
        payload = json.dumps({
            "record_id": record["record_id"],
            "task_name": record.get("Tên task", ""),
            "changes": fields,
            "group_chat_id": str(ctx.chat_id) if ctx.is_group else None,
        })
        await db_mod.create_approval(
            db_mod._db,
            str(ctx.boss_chat_id),
            str(ctx.sender_chat_id),
            record["record_id"],
            payload,
        )
        # Notify boss
        changes_str = ", ".join(
            f"{k}: {_ms_to_date(v) if k == 'Deadline' else v}"
            for k, v in fields.items()
        )
        boss = await db_mod.get_boss(str(ctx.boss_chat_id))
        if boss:
            await telegram.send(
                ctx.boss_chat_id,
                f"📝 Yêu cầu cập nhật task từ {ctx.sender_name}:\n\n"
                f"Task: {record.get('Tên task')}\n"
                f"Thay đổi: {changes_str}\n\n"
                f"Reply 'ok task {record.get('Tên task', '')}' để approve.",
            )
        return (f"Yêu cầu cập nhật '{record.get('Tên task')}' đã gửi đến sếp. "
                f"Bạn sẽ được thông báo khi được xử lý.")

    # Boss: apply directly
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


async def approve_task_change(ctx: ChatContext, approval_id: int) -> str:
    """Apply a pending task change and notify the requester."""
    import json
    from src import db
    from src.services import lark, telegram

    _db = await db.get_db()
    async with _db.execute(
        "SELECT * FROM pending_approvals WHERE id = ? AND boss_chat_id = ? AND status = 'pending'",
        (approval_id, str(ctx.boss_chat_id)),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return f"No pending approval found with id={approval_id}."

    approval = dict(row)
    payload = json.loads(approval["payload"]) if isinstance(approval["payload"], str) else approval["payload"]

    changes = payload.get("changes", {})
    record_id = payload.get("record_id", "")
    task_name = payload.get("task_name", "?")

    if changes and record_id:
        try:
            await lark.update_record(ctx.lark_base_token, ctx.lark_table_tasks, record_id, changes)
        except Exception as e:
            return f"Failed to apply changes to Lark: {e}"

    await _db.execute(
        "UPDATE pending_approvals SET status = 'approved' WHERE id = ?",
        (approval_id,),
    )
    await _db.commit()

    changes_str = ", ".join(f"{k}: {v}" for k, v in changes.items())
    try:
        await telegram.send(
            int(approval["requester_id"]),
            f"✅ Your update to task '{task_name}' was approved. Changes: {changes_str}",
        )
    except Exception:
        pass

    # Broadcast result to group if task was updated from group context
    group_chat_id = payload.get("group_chat_id")
    if group_chat_id:
        try:
            await telegram.send(
                int(group_chat_id),
                f"✅ Task *{task_name}* đã được duyệt cập nhật.",
            )
        except Exception:
            pass

    return f"Approved task change for '{task_name}'. Changes applied: {changes_str}"


async def reject_task_change(ctx: ChatContext, approval_id: int) -> str:
    """Reject a pending task change and notify the requester."""
    import json
    from src import db
    from src.services import telegram

    _db = await db.get_db()
    async with _db.execute(
        "SELECT * FROM pending_approvals WHERE id = ? AND boss_chat_id = ? AND status = 'pending'",
        (approval_id, str(ctx.boss_chat_id)),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return f"No pending approval found with id={approval_id}."

    approval = dict(row)
    payload = json.loads(approval["payload"]) if isinstance(approval["payload"], str) else approval["payload"]
    task_name = payload.get("task_name", "?")

    await _db.execute(
        "UPDATE pending_approvals SET status = 'rejected' WHERE id = ?",
        (approval_id,),
    )
    await _db.commit()

    try:
        await telegram.send(
            int(approval["requester_id"]),
            f"Your requested update to task '{task_name}' was not approved.",
        )
    except Exception:
        pass

    # Broadcast result to group if task was updated from group context
    group_chat_id = payload.get("group_chat_id")
    if group_chat_id:
        try:
            await telegram.send(
                int(group_chat_id),
                f"Task *{task_name}*: yêu cầu cập nhật không được duyệt.",
            )
        except Exception:
            pass

    return f"Rejected task change request for '{task_name}'."
