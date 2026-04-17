"""
identity.py — person identity helpers.

Principle:
  chat_id = primary key (Telegram unique per user).
  name    = hint (can collide, typo, nickname).

harvest(): passive index of observed chat_ids from Telegram updates.
resolve_candidates(): pull candidates from Lark + bosses + memberships + seen_contacts.

Both functions are stateless relative to agent flow — they do NOT mutate Lark
records or trigger messages. Agent explicitly decides linking via
link_contact_to_person tool.
"""
from __future__ import annotations

import logging
from typing import Any

from src import db
from src.context import ChatContext
from src.services import lark

logger = logging.getLogger("identity")


async def harvest(
    context_chat_id: int,
    sender: dict | None,
    mentions: list[dict] | None,
    reply_to: dict | None,
    new_members: list[dict] | None,
) -> None:
    """
    Fire-and-forget upsert into seen_contacts.

    context_chat_id: the chat (group or DM) where bot saw these people.
    sender: {id, name, username} — message author (may be None for non-user events).
    mentions: list of {id, name, username} from text_mention entities.
    reply_to: {id, name, username} of the replied-to user, or None.
    new_members: list of {id, name, username} just joined this chat.

    Swallows all exceptions — this is an index, not critical data.
    """
    try:
        contacts: list[dict] = []
        if sender and sender.get("id"):
            contacts.append(sender)
        for m in (mentions or []):
            if m.get("id"):
                contacts.append(m)
        if reply_to and reply_to.get("id"):
            contacts.append(reply_to)
        for m in (new_members or []):
            if m.get("id"):
                contacts.append(m)

        for c in contacts:
            await db.upsert_seen_contact(
                chat_id=int(c["id"]),
                display_name=c.get("name", ""),
                username=c.get("username", ""),
                last_seen_chat=context_chat_id,
            )
    except Exception:
        logger.warning("harvest failed", exc_info=True)


async def resolve_candidates(
    ctx: ChatContext,
    query: str,
    workspace_ids: str = "current",
) -> list[dict]:
    """
    Return list of candidate person dicts from all known sources.

    Each dict:
      {
        "chat_id": int | None,
        "name": str,
        "source": "lark_people" | "bosses" | "memberships" | "seen_contacts",
        "record_id": str | None,         # only for source=lark_people
        "workspace_name": str | None,    # only for source=lark_people
        "workspace_boss_id": int | None,
        "confidence": "exact_id" | "exact_name" | "partial_name" | "nickname_match",
      }

    Dedup by chat_id: prefer entries with record_id (lark_people) first.
    Order within source groups is source-priority:
      lark_people (current ws) → lark_people (other ws) → bosses → memberships → seen_contacts
    """
    from src.tools._workspace import resolve_workspaces

    q = (query or "").strip()
    if not q:
        return []

    q_lower = q.lower()
    q_tokens = {t for t in q_lower.split() if t}
    is_numeric_id = q.isdigit()

    def _name_match(text: str) -> str | None:
        """Bidirectional + token-level match. 'Linh' matches 'Nguyên Linh' and vice versa."""
        if not text:
            return None
        t = text.lower().strip()
        if q_lower == t:
            return "exact_name"
        # Token overlap — handles shortened / rearranged names
        t_tokens = {tok for tok in t.split() if tok}
        if q_tokens & t_tokens:
            return "partial_name"
        # Substring either direction — handles single-word names without space
        if q_lower in t or t in q_lower:
            return "partial_name"
        return None

    results: list[dict] = []

    # --- Source 1+2: Lark People across workspaces ---
    try:
        workspaces = await resolve_workspaces(ctx, workspace_ids)
    except Exception:
        workspaces = []

    for ws in workspaces:
        if not ws.get("lark_table_people"):
            continue
        try:
            records = await lark.search_records(ws["lark_base_token"], ws["lark_table_people"])
        except Exception:
            continue
        for r in records:
            full = str(r.get("Tên", ""))
            nick = str(r.get("Tên gọi", ""))
            note = str(r.get("Ghi chú", ""))
            raw_id = r.get("Chat ID")
            chat_id_val = None
            if raw_id:
                try:
                    chat_id_val = int(raw_id)
                except (ValueError, TypeError):
                    chat_id_val = None

            confidence = None
            if is_numeric_id and chat_id_val and str(chat_id_val) == q:
                confidence = "exact_id"
            else:
                confidence = _name_match(full) or _name_match(nick)
                if not confidence and note:
                    # Note may contain the person's alias — match tokens against note text
                    note_tokens = {tok.strip(".,;:()[]'\"") for tok in note.lower().split()}
                    if q_tokens & note_tokens:
                        confidence = "nickname_match"

            if not confidence:
                continue

            results.append({
                "chat_id": chat_id_val,
                "name": full or nick or "?",
                "source": "lark_people",
                "record_id": r.get("record_id"),
                "workspace_name": ws["workspace_name"],
                "workspace_boss_id": ws["boss_id"],
                "confidence": confidence,
            })

    # --- Source 3: bosses table ---
    _db = await db.get_db()
    try:
        async with _db.execute("SELECT chat_id, name FROM bosses") as cur:
            boss_rows = await cur.fetchall()
    except Exception:
        boss_rows = []

    for r in boss_rows:
        name = str(r["name"] or "")
        cid = int(r["chat_id"])
        if is_numeric_id and str(cid) == q:
            confidence = "exact_id"
        else:
            confidence = _name_match(name)
        if not confidence:
            continue
        results.append({
            "chat_id": cid,
            "name": name,
            "source": "bosses",
            "record_id": None,
            "workspace_name": None,
            "workspace_boss_id": cid,
            "confidence": confidence,
        })

    # --- Source 4: memberships ---
    try:
        async with _db.execute(
            "SELECT chat_id, boss_chat_id, name FROM memberships WHERE status='active'"
        ) as cur:
            mem_rows = await cur.fetchall()
    except Exception:
        mem_rows = []

    for r in mem_rows:
        name = str(r["name"] or "")
        cid_raw = r["chat_id"]
        try:
            cid = int(cid_raw) if cid_raw else None
        except (ValueError, TypeError):
            cid = None
        if cid is None:
            continue
        if is_numeric_id and str(cid) == q:
            confidence = "exact_id"
        else:
            confidence = _name_match(name)
        if not confidence:
            continue
        try:
            boss_id = int(r["boss_chat_id"]) if r["boss_chat_id"] else None
        except (ValueError, TypeError):
            boss_id = None
        results.append({
            "chat_id": cid,
            "name": name,
            "source": "memberships",
            "record_id": None,
            "workspace_name": None,
            "workspace_boss_id": boss_id,
            "confidence": confidence,
        })

    # --- Source 5: seen_contacts ---
    try:
        if is_numeric_id:
            direct = await db.get_seen_contact(int(q))
            seen_rows = [direct] if direct else []
        else:
            seen_rows = await db.search_seen_contacts(q_lower, limit=20)
    except Exception:
        seen_rows = []

    for r in seen_rows:
        cid = int(r["chat_id"])
        dname = str(r.get("display_name") or "")
        uname = str(r.get("username") or "")
        if is_numeric_id and str(cid) == q:
            confidence = "exact_id"
        else:
            confidence = _name_match(dname) or _name_match(uname)
        if not confidence:
            continue
        results.append({
            "chat_id": cid,
            "name": dname or uname or "?",
            "source": "seen_contacts",
            "record_id": None,
            "workspace_name": None,
            "workspace_boss_id": None,
            "confidence": confidence,
            "username": uname,
        })

    # --- Dedup by chat_id, prefer lark_people entries (has record_id) ---
    seen: dict[Any, dict] = {}
    for c in results:
        cid = c.get("chat_id")
        if cid is None:
            # No chat_id — keep as standalone (e.g., lark record without Chat ID)
            seen[id(c)] = c  # use python id() as unique key
            continue
        existing = seen.get(cid)
        if existing is None:
            seen[cid] = c
        else:
            # prefer lark_people over other sources
            if existing["source"] != "lark_people" and c["source"] == "lark_people":
                seen[cid] = c

    final = list(seen.values())

    # Preserve order: lark_people current ws first, then other ws, bosses, memberships, seen_contacts
    source_order = {"lark_people": 0, "bosses": 1, "memberships": 2, "seen_contacts": 3}
    final.sort(key=lambda c: (
        source_order.get(c["source"], 9),
        0 if c.get("workspace_boss_id") == ctx.boss_chat_id else 1,
    ))
    return final
