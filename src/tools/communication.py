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
    Unchanged signature; internals now use identity.resolve_candidates so we
    fall back to bosses/memberships/seen_contacts when Lark record lacks Chat ID.
    """
    from src import identity
    candidates = await identity.resolve_candidates(ctx, name, workspace_ids)
    linked = [c for c in candidates if c.get("chat_id")]
    if not linked:
        # Return first unlinked lark record's name (if any) so caller can report
        if candidates:
            return None, candidates[0]["name"], candidates[0].get("workspace_name") or ""
        return None, name, ""

    # Disambiguation: if in group, prefer candidates from this group's workspace
    if ctx.is_group and len(linked) > 1:
        preferred = [c for c in linked if c.get("workspace_boss_id") == ctx.boss_chat_id]
        if preferred:
            linked = preferred

    best = linked[0]
    return best["chat_id"], best["name"], best.get("workspace_name") or ""


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
    Returns 2 sections:
      1. Outbound log (from outbound_messages) — boss-initiated cross-workspace DMs.
      2. DM thread (from messages table, chat_id>0, role='assistant') — regular bot DMs.

    If person query has no resolvable chat_id, lists candidate chat_ids from
    other sources so agent can decide whether to link.

    since: "" | "today" | "YYYY-MM-DD" | "Nd" (e.g. "7d" = last 7 days). Filters both sections.
    log_type applies only to outbound log.
    """
    from src import identity

    to_chat_id: int | None = None
    resolved_name = person

    if person:
        candidates = await identity.resolve_candidates(ctx, person, workspace_ids)
        linked = [c for c in candidates if c.get("chat_id")]
        if linked:
            # prefer current workspace
            preferred = [c for c in linked if c.get("workspace_boss_id") == ctx.boss_chat_id]
            best = preferred[0] if preferred else linked[0]
            to_chat_id = best["chat_id"]
            resolved_name = best["name"]
        elif candidates:
            resolved_name = candidates[0]["name"]

        if to_chat_id is None:
            # No linked chat_id → surface state
            lines = [f"Chưa có Chat ID đã gắn cho '{person}'."]
            if candidates:
                lines.append("Ứng viên có chat_id từ nguồn khác:")
                for c in candidates:
                    if c.get("chat_id"):
                        lines.append(
                            f"  - chat_id={c['chat_id']} \"{c['name']}\" (source={c['source']})"
                        )
                lines.append(
                    "Có thể cùng 1 người — gọi link_contact_to_person để gắn "
                    "Chat ID vào Lark record nếu xác nhận."
                )
            else:
                lines.append("Không tìm thấy ứng viên nào khớp tên này.")
            return "\n".join(lines)

    # --- Normalize `since` to SQL filter ---
    # Accepts: "" (no filter) | "today" | "YYYY-MM-DD" | "Nd" (N days back)
    since_clause = ""
    since_params: tuple = ()
    if since:
        s = since.strip().lower()
        if s == "today":
            since_clause = " AND date(created_at) = date('now', 'localtime')"
        elif s.endswith("d") and s[:-1].isdigit():
            since_clause = f" AND created_at >= datetime('now', '-{int(s[:-1])} days')"
        else:
            try:
                from datetime import datetime as _dt
                _dt.strptime(since, "%Y-%m-%d")
                since_clause = " AND created_at >= ?"
                since_params = (since,)
            except ValueError:
                pass  # bad format — silently no-filter

    # --- Section 1: outbound_messages ---
    _db = await db.get_db()
    ob_conds = ["boss_chat_id = ?"]
    ob_params: list = [ctx.boss_chat_id]
    if to_chat_id:
        ob_conds.append("to_chat_id = ?")
        ob_params.append(to_chat_id)
    if log_type and log_type != "all":
        ob_conds.append("trigger_type = ?")
        ob_params.append(log_type)
    ob_where = " AND ".join(ob_conds) + since_clause
    async with _db.execute(
        f"SELECT * FROM outbound_messages WHERE {ob_where} ORDER BY created_at DESC LIMIT 30",
        tuple(ob_params) + since_params,
    ) as cur:
        outbound_rows = [dict(r) for r in await cur.fetchall()]

    # --- Section 2: messages table (DM thread) ---
    dm_rows: list[dict] = []
    if to_chat_id and to_chat_id > 0:
        async with _db.execute(
            f"""SELECT created_at, substr(content, 1, 200) AS content
                FROM messages
                WHERE chat_id = ? AND role = 'assistant'{since_clause}
                ORDER BY id DESC LIMIT 30""",
            (to_chat_id,) + since_params,
        ) as cur:
            rows = await cur.fetchall()
        dm_rows = [dict(r) for r in rows]

    # --- Compose output ---
    subject = f"với {resolved_name}" if person else "với toàn team"
    out_lines: list[str] = []

    out_lines.append(f"=== Outbound log (tool send_dm / task-notify / reminder) — {subject} ===")
    if outbound_rows:
        for r in outbound_rows:
            dt = (r.get("created_at") or "")[:16]
            trig = r.get("trigger_type", "")
            to = r.get("to_name", "")
            preview = (r.get("content") or "")[:80]
            out_lines.append(f"  [{dt}] → {to} ({trig}): {preview}")
    else:
        out_lines.append("  (trống)")

    out_lines.append("")
    out_lines.append(f"=== DM thread (bot ↔ người này qua workspace của họ) — {subject} ===")
    if dm_rows:
        for r in dm_rows:
            dt = (r.get("created_at") or "")[:16]
            preview = (r.get("content") or "")[:80]
            out_lines.append(f"  [{dt}] bot: {preview}")
    elif to_chat_id and to_chat_id > 0:
        out_lines.append("  (chưa có DM thread nào)")
    else:
        out_lines.append("  (không áp dụng — không resolve được chat_id)")

    return "\n".join(out_lines)


async def resolve_person(
    ctx: ChatContext,
    query: str,
    workspace_ids: str = "current",
) -> str:
    """
    Trả danh sách tất cả ứng viên người khớp query (tên/nickname/chat_id số).

    Liệt kê từ mọi nguồn: Lark People, bosses, memberships, seen_contacts.
    Agent đọc và tự quyết định ai là đúng — tool KHÔNG tự chọn.
    """
    from src import identity
    candidates = await identity.resolve_candidates(ctx, query, workspace_ids)
    if not candidates:
        return f"Không tìm thấy ai khớp '{query}' trong mọi nguồn dữ liệu."

    lines = [f"Kết quả resolve '{query}' ({len(candidates)} ứng viên):"]
    chat_id_groups: dict[int, list[int]] = {}  # chat_id -> list of result indices
    for i, c in enumerate(candidates, 1):
        parts = [f"{i}."]
        parts.append(f"chat_id={c.get('chat_id') if c.get('chat_id') else 'null'}")
        parts.append(f"name=\"{c['name']}\"")
        parts.append(f"source={c['source']}")
        if c.get("workspace_name"):
            parts.append(f"workspace=\"{c['workspace_name']}\"")
        if c.get("record_id"):
            parts.append(f"record_id={c['record_id']}")
        if c.get("username"):
            parts.append(f"username=\"{c['username']}\"")
        parts.append(f"confidence={c['confidence']}")
        lines.append(" | ".join(parts))

        cid = c.get("chat_id")
        if cid is not None:
            chat_id_groups.setdefault(cid, []).append(i)

    # Annotate chat_id collisions
    for cid, idxs in chat_id_groups.items():
        if len(idxs) >= 2:
            lines.append(
                f"Lưu ý: các dòng {', '.join(map(str, idxs))} cùng chat_id={cid} → cùng 1 người."
            )

    # Annotate lark records with no chat_id
    no_id_idx = [i + 1 for i, c in enumerate(candidates)
                 if c["source"] == "lark_people" and c.get("chat_id") is None]
    if no_id_idx:
        lines.append(
            f"Lưu ý: dòng {', '.join(map(str, no_id_idx))} là Lark record chưa có Chat ID — "
            f"có thể gọi link_contact_to_person để gắn."
        )

    return "\n".join(lines)


async def link_contact_to_person(
    ctx: ChatContext,
    chat_id: int,
    lark_record_id: str,
    workspace_ids: str = "current",
) -> str:
    """
    Gắn chat_id vào trường "Chat ID" của 1 Lark People record.
    Dùng khi agent xác định seen_contacts/bosses chính là record Lark thiếu Chat ID.

    Fails loud nếu record đã có Chat ID khác (conflict) — không auto-overwrite.
    """
    from src.tools._workspace import resolve_workspaces
    workspaces = await resolve_workspaces(ctx, workspace_ids)

    # Locate the record across resolved workspaces
    target_ws = None
    target_record = None
    for ws in workspaces:
        if not ws.get("lark_table_people"):
            continue
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_people"])
        except Exception:
            continue
        for r in records:
            if r.get("record_id") == lark_record_id:
                target_ws = ws
                target_record = r
                break
        if target_record:
            break

    if not target_record:
        return f"[TOOL_ERROR:not_found] Không tìm thấy Lark record '{lark_record_id}' trong workspace(s)."

    existing = target_record.get("Chat ID")
    if existing:
        try:
            existing_int = int(existing)
        except (ValueError, TypeError):
            existing_int = None
        if existing_int == int(chat_id):
            return f"Record '{lark_record_id}' ({target_record.get('Tên', '?')}) đã có Chat ID={chat_id}. Không cần thay."
        return (
            f"[CONFLICT] Record '{lark_record_id}' ({target_record.get('Tên', '?')}) "
            f"đã có Chat ID={existing} khác {chat_id}. "
            f"Cần xác nhận trước khi overwrite (gọi lại với chat_id này sau khi boss đồng ý)."
        )

    # Perform update
    try:
        await lark.update_record(
            target_ws["lark_base_token"],
            target_ws["lark_table_people"],
            lark_record_id,
            {"Chat ID": int(chat_id)},
        )
    except Exception as e:
        return f"[TOOL_ERROR:lark] Không ghi được Chat ID vào Lark: {e}"

    # Also insert into people_map so SQLite-side flows can find this person
    name = target_record.get("Tên", "")
    person_type = target_record.get("Type", "member")
    try:
        await db.add_person(
            chat_id=int(chat_id),
            boss_chat_id=ctx.boss_chat_id,
            person_type=person_type,
            name=name,
        )
    except Exception:
        logger.warning("link_contact_to_person: add_person failed (non-fatal)", exc_info=True)

    return f"Đã gắn chat_id={chat_id} vào Lark record '{lark_record_id}' ({name})."


async def list_unlinked_contacts(
    ctx: ChatContext,
    days: int = 30,
    limit: int = 30,
) -> str:
    """
    Liệt kê chat_id bot đã thấy trong group/DM qua Telegram nhưng CHƯA được
    gắn vào bất kỳ Lark People record nào (của boss hiện tại).

    Dùng để agent review + gọi link_contact_to_person khi cần.
    """
    # Collect chat_ids already present in current workspace's Lark People
    lark_chat_ids: set[int] = set()
    try:
        records = await lark.search_records(ctx.lark_base_token, ctx.lark_table_people)
        for r in records:
            cid = r.get("Chat ID")
            if cid:
                try:
                    lark_chat_ids.add(int(cid))
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass

    unlinked = await db.list_unlinked_seen_contacts(
        lark_people_chat_ids=lark_chat_ids,
        days=days,
        limit=limit,
    )

    if not unlinked:
        return f"Không có chat_id nào thấy trong {days} ngày qua mà chưa gắn Lark record."

    lines = [f"Chat IDs đã thấy ({days} ngày, {len(unlinked)} mục) nhưng CHƯA gắn Lark People (current workspace):"]
    for r in unlinked:
        last = (r.get("last_seen_at") or "")[:16]
        name = r.get("display_name") or "?"
        uname = r.get("username") or ""
        ctx_chat = r.get("last_seen_chat")
        lines.append(
            f"  chat_id={r['chat_id']} | \"{name}\""
            + (f" | @{uname}" if uname else "")
            + f" | last_seen={last}"
            + (f" in chat {ctx_chat}" if ctx_chat else "")
        )
    lines.append("Dùng link_contact_to_person(chat_id, lark_record_id) để gắn khi xác nhận được danh tính.")
    return "\n".join(lines)


async def get_group_admins(ctx: ChatContext) -> str:
    """
    Trả danh sách admin của group hiện tại (chỉ khi trong group context).
    Không list được non-admin members (Telegram API giới hạn).
    """
    if not ctx.is_group:
        return "Tool này chỉ chạy trong context group."

    admins = await telegram.get_chat_administrators(ctx.chat_id)
    if not admins:
        return "Không lấy được danh sách admin (có thể bot chưa là thành viên, hoặc API lỗi)."

    lines = [f"Admins của group này ({len(admins)} người):"]
    for a in admins:
        parts = [f"chat_id={a['user_id']}", f"name=\"{a['name']}\""]
        if a.get("username"):
            parts.append(f"@{a['username']}")
        if a.get("status"):
            parts.append(f"status={a['status']}")
        lines.append("  - " + " | ".join(parts))
    return "\n".join(lines)
