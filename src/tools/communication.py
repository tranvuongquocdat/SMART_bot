"""
Communication tools — send DM, broadcast, get communication log.
All outbound DMs are logged to outbound_messages table.
"""
import logging

from src import db
from src.context import ChatContext
from src.services import lark, telegram

logger = logging.getLogger("tools.communication")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _find_person_chat_id(
    ctx: ChatContext, name: str, workspace_ids: str = "current"
) -> tuple[int | None, str, str]:
    """
    Returns (chat_id, resolved_name, workspace_name).
    Disambiguation: group context → prefer group's workspace first.
    Returns (None, name, "") if person not found or has no Chat ID.
    """
    from src.tools._workspace import resolve_workspaces
    workspaces = await resolve_workspaces(ctx, workspace_ids)
    candidates = []
    for ws in workspaces:
        if not ws.get("lark_table_people"):
            continue
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_people"])
        except Exception:
            continue
        for r in records:
            full_name = r.get("Tên", "")
            nickname = r.get("Tên gọi", "")
            if name.lower() in full_name.lower() or (nickname and name.lower() in nickname.lower()):
                raw_id = r.get("Chat ID")
                candidates.append({
                    "chat_id": int(raw_id) if raw_id else None,
                    "name": full_name,
                    "workspace_name": ws["workspace_name"],
                    "workspace_boss_id": ws["boss_id"],
                })

    if not candidates:
        return None, name, ""

    # Disambiguation: if in group, prefer workspace matching group's boss
    if ctx.is_group and len(candidates) > 1:
        preferred = [c for c in candidates if c["workspace_boss_id"] == ctx.boss_chat_id]
        if preferred:
            candidates = preferred

    best = candidates[0]
    return best["chat_id"], best["name"], best["workspace_name"]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

async def send_dm(
    ctx: ChatContext,
    to: str,
    content: str,
    context: str = "",
    workspace_ids: str = "current",
) -> str:
    """
    Send a private DM to a team member by name.
    Logs the message to outbound_messages.
    Use this when boss wants to message someone privately — even from a group context.
    Disambiguation: if in a group, searches that group's workspace first.
    """
    chat_id, resolved_name, workspace_name = await _find_person_chat_id(ctx, to, workspace_ids)

    if chat_id is None and resolved_name == to:
        return f"[TOOL_ERROR:not_found] Không tìm thấy '{to}' trong danh sách nhân sự."

    if chat_id is None:
        return (
            f"{resolved_name} có trong danh sách nhưng chưa có tài khoản liên kết — "
            f"không thể nhắn tin trực tiếp."
        )

    message_text = f"Tin nhắn từ {ctx.boss_name}:\n\n{content}"
    await telegram.send(chat_id, message_text)

    await db.log_outbound_dm(
        boss_chat_id=ctx.boss_chat_id,
        to_chat_id=chat_id,
        to_name=resolved_name,
        content=content,
        trigger_type="manual",
        workspace_id=workspace_name,
    )

    return (
        f"Đã nhắn tin riêng cho {resolved_name}"
        + (f" [{workspace_name}]" if workspace_name else "")
        + "."
    )


async def broadcast(
    ctx: ChatContext,
    message: str,
    targets: str = "all_members",
    workspace_ids: str = "current",
) -> str:
    """
    Send a message to multiple people individually via DM.
    targets: "all_members" | "all_partners" | "all" | comma-separated names.
    Works from both group and DM context.
    Use check_team_engagement first to know who has Chat IDs.
    """
    from src.tools._workspace import resolve_workspaces
    workspaces = await resolve_workspaces(ctx, workspace_ids)

    type_filter = None
    specific_names: list[str] = []
    if targets in ("all_members", "all_partners", "all"):
        if targets == "all_members":
            type_filter = "Nhân viên"
        elif targets == "all_partners":
            type_filter = "Cộng tác viên"
        # "all" → no filter
    else:
        specific_names = [n.strip() for n in targets.split(",")]

    sent, failed = [], []
    seen_chat_ids: set[int] = set()

    for ws in workspaces:
        if not ws.get("lark_table_people"):
            continue
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_people"])
        except Exception:
            continue

        for r in records:
            name = r.get("Tên", "")
            ptype = r.get("Type", "")

            if specific_names and not any(n.lower() in name.lower() for n in specific_names):
                continue
            if type_filter and ptype != type_filter:
                continue

            raw_id = r.get("Chat ID")
            if not raw_id:
                failed.append(f"{name} (không có Chat ID)")
                continue

            chat_id = int(raw_id)
            if chat_id in seen_chat_ids:
                continue
            seen_chat_ids.add(chat_id)

            try:
                await telegram.send(chat_id, f"Thông báo từ {ctx.boss_name}:\n\n{message}")
                await db.log_outbound_dm(
                    boss_chat_id=ctx.boss_chat_id,
                    to_chat_id=chat_id,
                    to_name=name,
                    content=message,
                    trigger_type="manual",
                    workspace_id=ws["workspace_name"],
                )
                sent.append(name)
            except Exception as e:
                failed.append(f"{name} (lỗi: {e})")

    parts = [f"Đã gửi cho {len(sent)} người: {', '.join(sent)}."] if sent else ["Không gửi được cho ai."]
    if failed:
        parts.append(f"Không gửi được cho: {', '.join(failed)}.")
    return " ".join(parts)


async def get_communication_log(
    ctx: ChatContext,
    person: str = "",
    since: str = "",
    log_type: str = "all",
    workspace_ids: str = "current",
) -> str:
    """
    Returns full timeline of all bot-initiated contact with a person or the whole team.
    log_type: "all" | "manual" | "task_assigned" | "deadline_push" | "reminder"
    Call this before answering 'đã nhắn X chưa' or 'đã push deadline chưa'.
    Tracks from redesign deployment — no historical backfill.
    """
    to_chat_id = None
    resolved_name = person
    if person:
        chat_id, resolved_name, _ = await _find_person_chat_id(ctx, person, workspace_ids)
        to_chat_id = chat_id

    rows = await db.get_outbound_log(
        boss_chat_id=ctx.boss_chat_id,
        to_chat_id=to_chat_id,
        trigger_type=log_type if log_type != "all" else None,
        limit=30,
    )

    if not rows:
        subject = f"với {resolved_name}" if person else "với bất kỳ ai"
        return f"Chưa có lịch sử nhắn tin {subject}."

    lines = [f"Lịch sử tin nhắn{' với ' + resolved_name if person else ''} ({len(rows)} mục):"]
    for r in rows:
        dt = r.get("created_at", "")[:16]
        trigger = r.get("trigger_type", "")
        to = r.get("to_name", "")
        content_preview = r.get("content", "")[:80]
        lines.append(f"  [{dt}] → {to} ({trigger}): {content_preview}")
    return "\n".join(lines)
