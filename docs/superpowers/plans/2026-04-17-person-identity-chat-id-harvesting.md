# Person Identity & Chat-ID Harvesting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bot thu thập chat_id từ mọi nơi Telegram đã đưa sẵn (entities, reply, new_chat_members, sender), expose state qua tool (không hardcode flow), để agent tự resolve người được hỏi kể cả khi Lark record thiếu Chat ID.

**Architecture:** 5-layer — (1) parse Telegram update, (2) passive harvest vào `seen_contacts` table, (3) identity resolver trả candidates, (4) expanded communication log đọc cả `messages`, (5) explicit `link_contact_to_person` tool. Tool returns raw state; agent tự interpret.

**Tech Stack:** Python 3.11+, aiosqlite, httpx (async), existing telegram polling, Lark Bitable API.

**Testing:** User chỉ đạo skip unit test lần này — làm manual smoke test cuối. Mỗi task kết thúc bằng commit.

**Reference spec:** [docs/superpowers/specs/2026-04-17-person-identity-chat-id-harvesting-design.md](../specs/2026-04-17-person-identity-chat-id-harvesting-design.md)

---

## File Structure

| File | Kiểu | Trách nhiệm |
|---|---|---|
| `src/services/lark.py` | Mở rộng | Check Lark business code trong `update_record` |
| `src/db.py` | Mở rộng | Schema + helpers cho `seen_contacts` |
| `src/services/telegram.py` | Mở rộng | Parse entities/reply/new_members; `get_chat_administrators` helper |
| `src/agent.py` | Mở rộng | Nhận kwargs mới; spawn harvest; THINKING_MAP + SECRETARY_PROMPT updates |
| `src/identity.py` | Mới | `harvest()`, `resolve_candidates()` |
| `src/tools/communication.py` | Mở rộng | Refactor `_find_person_chat_id`; expand `get_communication_log`; 4 tool mới |
| `src/tools/__init__.py` | Mở rộng | Đăng ký 4 tool mới vào `TOOL_DEFINITIONS` + `_dispatch_tool` |

---

## Task 1: Fix `lark.update_record` để surface business errors

**Rationale:** Layer 5 `link_contact_to_person` cần Lark fail loud khi ghi thất bại. Hiện `update_record` chỉ check HTTP status, bỏ qua `body.code != 0` (Lark trả 200 nhưng code=nonzero cho lỗi nghiệp vụ như field sai, permission).

**Files:**
- Modify: `src/services/lark.py:252-259`

- [ ] **Step 1: Đọc code hiện tại**

Xem [src/services/lark.py:252-259](src/services/lark.py#L252-L259). Hàm chưa check `body.code`.

- [ ] **Step 2: Thêm check `body.code != 0`**

Thay thế hàm cũ:

```python
async def update_record(base_token: str, table_id: str, record_id: str, fields: dict) -> dict:
    resp = await _client.put(
        f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records/{record_id}",
        headers=await _headers(),
        json={"fields": fields},
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise Exception(f"Lark error: {body.get('code')} - {body.get('msg')}")
    return body["data"]["record"]
```

- [ ] **Step 3: Cùng pattern cho `search_records` (cùng 1 file)**

Thay thế [src/services/lark.py:237-249](src/services/lark.py#L237-L249):

```python
async def search_records(base_token: str, table_id: str, filter_expr: str = "") -> list[dict]:
    params = {"page_size": 100}
    if filter_expr:
        params["filter"] = filter_expr
    resp = await _client.get(
        f"{LARK_API}/bitable/v1/apps/{base_token}/tables/{table_id}/records",
        headers=await _headers(),
        params=params,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise Exception(f"Lark error: {body.get('code')} - {body.get('msg')}")
    data = body.get("data", {})
    items = data.get("items", [])
    return [{"record_id": r["record_id"], **r["fields"]} for r in items]
```

- [ ] **Step 4: Sanity check vẫn chạy với data thật**

Run:
```bash
cd /home/dat/2026/SMART_bot && python3 -c "
import asyncio, os
from dotenv import load_dotenv; load_dotenv()
from src.services import lark
async def main():
    await lark.init_lark(os.environ['LARK_APP_ID'], os.environ['LARK_APP_SECRET'])
    rows = await lark.search_records('ZeuxbOnWAaEB6os1jqBl217jg3f', 'tblAolWztqcs8Ifl')
    print('people count:', len(rows))
    await lark.close_lark()
asyncio.run(main())
"
```
Expected: `people count: 2` (Đạt + Nguyên Linh)

- [ ] **Step 5: Commit**

```bash
git add src/services/lark.py
git commit -m "fix(lark): surface business errors in update_record/search_records

body.code != 0 now raises (was silently treated as success). Required for
reliable Lark-first writes."
```

---

## Task 2: DB schema + helpers cho `seen_contacts`

**Files:**
- Modify: `src/db.py` — thêm schema trong `_init_schema` + helpers

- [ ] **Step 1: Locate schema init function**

Tìm hàm init schema trong [src/db.py](src/db.py):
```bash
grep -n "CREATE TABLE" src/db.py | head -20
```
Thêm schema mới cạnh các `CREATE TABLE` khác (ví dụ sau `onboarding_state`).

- [ ] **Step 2: Thêm CREATE TABLE**

Trong hàm init schema, thêm:

```python
await db.execute("""
    CREATE TABLE IF NOT EXISTS seen_contacts (
        chat_id          INTEGER PRIMARY KEY,
        display_name     TEXT,
        username         TEXT,
        first_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_seen_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_seen_chat   INTEGER,
        seen_count       INTEGER DEFAULT 1
    )
""")
await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_seen_contacts_name
        ON seen_contacts (display_name)
""")
await db.execute("""
    CREATE INDEX IF NOT EXISTS idx_seen_contacts_username
        ON seen_contacts (username)
""")
```

- [ ] **Step 3: Thêm helpers cuối file `src/db.py`**

```python
async def upsert_seen_contact(
    chat_id: int,
    display_name: str = "",
    username: str = "",
    last_seen_chat: int | None = None,
) -> None:
    """Insert or update a seen contact; bumps last_seen_at and seen_count."""
    _db = await get_db()
    await _db.execute(
        """
        INSERT INTO seen_contacts (chat_id, display_name, username, last_seen_chat)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            display_name   = COALESCE(NULLIF(excluded.display_name, ''), seen_contacts.display_name),
            username       = COALESCE(NULLIF(excluded.username, ''), seen_contacts.username),
            last_seen_at   = CURRENT_TIMESTAMP,
            last_seen_chat = COALESCE(excluded.last_seen_chat, seen_contacts.last_seen_chat),
            seen_count     = seen_contacts.seen_count + 1
        """,
        (chat_id, display_name or "", username or "", last_seen_chat),
    )
    await _db.commit()


async def get_seen_contact(chat_id: int) -> dict | None:
    _db = await get_db()
    async with _db.execute(
        "SELECT * FROM seen_contacts WHERE chat_id = ?", (chat_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def search_seen_contacts(query: str, limit: int = 20) -> list[dict]:
    """Tìm contacts theo display_name hoặc username (substring, case-insensitive)."""
    _db = await get_db()
    like = f"%{query.lower()}%"
    async with _db.execute(
        """SELECT * FROM seen_contacts
           WHERE lower(display_name) LIKE ? OR lower(username) LIKE ?
           ORDER BY last_seen_at DESC LIMIT ?""",
        (like, like, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def list_unlinked_seen_contacts(
    lark_people_chat_ids: set[int],
    days: int = 30,
    limit: int = 30,
) -> list[dict]:
    """
    Trả seen_contacts mà chat_id KHÔNG có trong set lark_people_chat_ids
    (do caller truyền vào), sort theo last_seen_at DESC.
    Caller phải load Lark People chat_ids trước để so.
    """
    _db = await get_db()
    async with _db.execute(
        """SELECT * FROM seen_contacts
           WHERE last_seen_at >= datetime('now', ? )
           ORDER BY last_seen_at DESC LIMIT ?""",
        (f"-{days} days", limit * 3),  # overfetch để còn đủ sau filter
    ) as cur:
        rows = await cur.fetchall()
    filtered = [dict(r) for r in rows if dict(r)["chat_id"] not in lark_people_chat_ids]
    return filtered[:limit]
```

- [ ] **Step 4: Smoke verify schema applied**

```bash
cd /home/dat/2026/SMART_bot && python3 -c "
import asyncio
from src import db as d
async def main():
    _db = await d.get_db('data/history.db')
    async with _db.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='seen_contacts'\") as c:
        row = await c.fetchone()
    print('seen_contacts exists:', bool(row))
asyncio.run(main())
"
```
Expected: `seen_contacts exists: True`

- [ ] **Step 5: Commit**

```bash
git add src/db.py
git commit -m "feat(db): add seen_contacts table + helpers

Passive index of chat_ids bot has observed via Telegram updates
(sender/mentions/reply/new_members). Used by identity resolver and
link_contact_to_person tool."
```

---

## Task 3: Telegram `get_chat_administrators` helper + cache

**Files:**
- Modify: `src/services/telegram.py` — thêm hàm mới cuối file

- [ ] **Step 1: Thêm hàm + cache in-memory**

Thêm vào cuối `src/services/telegram.py`:

```python
# --- Admin list cache (10 min TTL) ---
_admins_cache: dict[int, tuple[float, list[dict]]] = {}
_ADMIN_TTL = 600  # seconds


async def get_chat_administrators(chat_id: int) -> list[dict]:
    """
    Returns list of admin members: [{user_id, name, username, status}, ...].
    Cached per-chat for 10 minutes.
    Privacy note: bot không list được non-admin members (Telegram API limit).
    """
    import time as _time
    now = _time.time()
    cached = _admins_cache.get(chat_id)
    if cached and now - cached[0] < _ADMIN_TTL:
        return cached[1]

    resp = await _client.post(
        f"{API}/bot{_token}/getChatAdministrators",
        json={"chat_id": chat_id},
        timeout=10,
    )
    data = resp.json()
    if not data.get("ok"):
        logger.warning("getChatAdministrators failed for %s: %s", chat_id, data)
        return []

    result = []
    for m in data.get("result", []):
        user = m.get("user", {})
        if user.get("is_bot"):
            continue
        result.append({
            "user_id": user.get("id"),
            "name": (user.get("first_name", "") + " " + user.get("last_name", "")).strip(),
            "username": user.get("username", ""),
            "status": m.get("status", ""),
        })
    _admins_cache[chat_id] = (now, result)
    return result
```

- [ ] **Step 2: Commit**

```bash
git add src/services/telegram.py
git commit -m "feat(telegram): add cached get_chat_administrators helper

10-min in-memory cache. Skips bot accounts. Used by future
get_group_admins tool for agent-driven admin discovery."
```

---

## Task 4: Parse entities / reply / new_chat_members trong `start_polling`

**Files:**
- Modify: `src/services/telegram.py:56-115` — hàm `start_polling`

- [ ] **Step 1: Thay hàm `start_polling`**

Thay thế nội dung hàm `start_polling` (line 56 trở đi) bằng:

```python
async def start_polling(on_message):
    """
    Long polling loop.

    on_message callback signature (backward-compatible qua kwargs):
        on_message(text, chat_id, sender_id, is_group, bot_mentioned, group_name,
                   *, sender_name="", mentions=None, username_mentions=None,
                   reply_to=None, new_members=None)

    New kwargs:
      sender_name: display name from message.from
      mentions: [{id, name, username}] từ entities type=text_mention
      username_mentions: [str] — @username text chưa resolve user_id
      reply_to: {id, name, username} or None
      new_members: [{id, name, username}] từ new_chat_members
    """
    global _polling
    _polling = True

    me_resp = await _client.get(f"{API}/bot{_token}/getMe")
    bot_username = me_resp.json().get("result", {}).get("username", "")
    logger.info("Polling started as @%s", bot_username)

    offset = 0

    while _polling:
        try:
            resp = await _client.get(
                f"{API}/bot{_token}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35.0,
            )
            updates = resp.json().get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message", {})
                text = message.get("text", "")
                chat = message.get("chat", {})
                chat_id = chat.get("id")
                from_user = message.get("from", {}) or {}
                sender_id = from_user.get("id")
                chat_type = chat.get("type", "")

                # new_chat_members event can come without text
                new_members_raw = message.get("new_chat_members", []) or []

                if not chat_id:
                    continue
                if not text and not new_members_raw:
                    continue

                is_group = chat_type in ("group", "supergroup")
                bot_mentioned = bool(bot_username) and f"@{bot_username}" in (text or "")
                group_name = chat.get("title", "") if is_group else ""

                # --- Harvest identity data from update ---
                sender_name = _full_name(from_user)

                mentions: list[dict] = []
                username_mentions: list[str] = []
                for ent in (message.get("entities") or []):
                    etype = ent.get("type")
                    if etype == "text_mention":
                        u = ent.get("user", {}) or {}
                        if u.get("id"):
                            mentions.append({
                                "id": u["id"],
                                "name": _full_name(u),
                                "username": u.get("username", ""),
                            })
                    elif etype == "mention":
                        # @username substring from text; offset+length addresses
                        off = ent.get("offset", 0)
                        length = ent.get("length", 0)
                        mention_text = (text or "")[off:off + length].lstrip("@")
                        if mention_text:
                            username_mentions.append(mention_text)

                reply_to = None
                rt = message.get("reply_to_message", {})
                if rt:
                    rt_from = rt.get("from", {}) or {}
                    if rt_from.get("id"):
                        reply_to = {
                            "id": rt_from["id"],
                            "name": _full_name(rt_from),
                            "username": rt_from.get("username", ""),
                        }

                new_members: list[dict] = []
                for m in new_members_raw:
                    if m.get("is_bot"):
                        continue
                    if m.get("id"):
                        new_members.append({
                            "id": m["id"],
                            "name": _full_name(m),
                            "username": m.get("username", ""),
                        })

                logger.info(
                    "[chat:%s type:%s sender:%s] Received: %s",
                    chat_id, chat_type, sender_id, (text or "")[:100],
                )
                asyncio.create_task(
                    on_message(
                        text or "", chat_id, sender_id, is_group, bot_mentioned, group_name,
                        sender_name=sender_name,
                        mentions=mentions,
                        username_mentions=username_mentions,
                        reply_to=reply_to,
                        new_members=new_members,
                    )
                )

        except httpx.ReadTimeout:
            continue
        except Exception:
            logger.exception("Polling error, retrying in 3s")
            await asyncio.sleep(3)


def _full_name(user: dict) -> str:
    """Join first_name + last_name, stripped."""
    return (f"{user.get('first_name', '')} {user.get('last_name', '')}").strip()
```

- [ ] **Step 2: Smoke run bot + kiểm tra log khi có mention**

(Manual — không tự động được; agent nhớ hướng dẫn user lúc smoke test cuối).

- [ ] **Step 3: Commit**

```bash
git add src/services/telegram.py
git commit -m "feat(telegram): parse entities/reply/new_chat_members in poller

Passes sender_name/mentions/username_mentions/reply_to/new_members as
kwargs to on_message callback. Backward-compatible — existing callers
ignoring new kwargs still work. Source for identity harvesting."
```

---

## Task 5: Mở rộng `agent.handle_message` signature (pass-through)

**Files:**
- Modify: `src/agent.py:204-211`

- [ ] **Step 1: Đổi signature (chỉ thêm kwargs, chưa dùng logic)**

Thay thế đoạn bắt đầu hàm (line 204):

```python
async def handle_message(
    text: str,
    chat_id: int,
    sender_id: int,
    is_group: bool,
    bot_mentioned: bool,
    group_name: str = "",
    *,
    sender_name: str = "",
    mentions: list[dict] | None = None,
    username_mentions: list[str] | None = None,
    reply_to: dict | None = None,
    new_members: list[dict] | None = None,
):
    start_time = time.time()
    log_prefix = f"[chat:{chat_id} sender:{sender_id}]"
    mentions = mentions or []
    username_mentions = username_mentions or []
    new_members = new_members or []

    logger.info("%s >>> INPUT: %s", log_prefix, text[:200])
```

(Chưa đụng logic body — pass-through chuẩn bị cho Task 7.)

- [ ] **Step 2: Commit**

```bash
git add src/agent.py
git commit -m "feat(agent): extend handle_message signature for identity kwargs

Accepts sender_name/mentions/username_mentions/reply_to/new_members as
keyword-only args with safe defaults. No behavior change yet — prepares
for harvest hook in next commit."
```

---

## Task 6: Create `src/identity.py` — `harvest()` function

**Files:**
- Create: `src/identity.py`

- [ ] **Step 1: Viết module mới**

```python
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
    is_numeric_id = q.isdigit()

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
            elif q_lower == full.lower() or (nick and q_lower == nick.lower()):
                confidence = "exact_name"
            elif q_lower in full.lower():
                confidence = "partial_name"
            elif nick and q_lower in nick.lower():
                confidence = "nickname_match"
            elif note and q_lower in note.lower():
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
    try:
        _db = await db.get_db()
        async with _db.execute("SELECT chat_id, name FROM bosses") as cur:
            boss_rows = await cur.fetchall()
    except Exception:
        boss_rows = []

    for r in boss_rows:
        name = str(r["name"] or "")
        cid = int(r["chat_id"])
        confidence = None
        if is_numeric_id and str(cid) == q:
            confidence = "exact_id"
        elif q_lower == name.lower():
            confidence = "exact_name"
        elif q_lower in name.lower():
            confidence = "partial_name"
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
        confidence = None
        if is_numeric_id and str(cid) == q:
            confidence = "exact_id"
        elif q_lower == name.lower():
            confidence = "exact_name"
        elif q_lower in name.lower():
            confidence = "partial_name"
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
        confidence = None
        if is_numeric_id and str(cid) == q:
            confidence = "exact_id"
        elif q_lower == dname.lower() or (uname and q_lower == uname.lower()):
            confidence = "exact_name"
        elif q_lower in dname.lower() or (uname and q_lower in uname.lower()):
            confidence = "partial_name"
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
    seen: dict[int, dict] = {}
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

    # Re-add no-chat-id entries that weren't captured
    final = list(seen.values())

    # Preserve order: lark_people current ws first, then other ws, bosses, memberships, seen_contacts
    source_order = {"lark_people": 0, "bosses": 1, "memberships": 2, "seen_contacts": 3}
    final.sort(key=lambda c: (
        source_order.get(c["source"], 9),
        0 if c.get("workspace_boss_id") == ctx.boss_chat_id else 1,
    ))
    return final
```

- [ ] **Step 2: Smoke test module imports và resolve_candidates chạy**

```bash
cd /home/dat/2026/SMART_bot && python3 -c "
import asyncio
from src import db, context
from src import identity

class FakeCtx:
    boss_chat_id = 5865065981
    lark_base_token = 'ZeuxbOnWAaEB6os1jqBl217jg3f'
    lark_table_people = 'tblAolWztqcs8Ifl'
    is_group = False
    all_memberships = []

async def main():
    import os
    from dotenv import load_dotenv; load_dotenv()
    from src.services import lark as larksvc
    await larksvc.init_lark(os.environ['LARK_APP_ID'], os.environ['LARK_APP_SECRET'])
    await db.get_db('data/history.db')
    ctx = FakeCtx()
    cands = await identity.resolve_candidates(ctx, 'Linh', workspace_ids='current')
    for c in cands:
        print(c)
    await larksvc.close_lark()
asyncio.run(main())
"
```
Expected: ít nhất 2 candidates — 1 từ `lark_people` ("Nguyên Linh", no chat_id) + 1 từ `bosses` ("Linh", chat_id=8638723771).

(Note: `FakeCtx` có thể thiếu field — nếu `resolve_workspaces` yêu cầu full ChatContext, sử dụng real context. Có thể skip smoke test Task 6 và test chung ở cuối.)

- [ ] **Step 3: Commit**

```bash
git add src/identity.py
git commit -m "feat(identity): add harvest() and resolve_candidates()

harvest(): upsert chat_ids observed in Telegram updates into seen_contacts.
resolve_candidates(): pull matching candidates from Lark people, bosses,
memberships, seen_contacts — dedup by chat_id, priority-ordered.

chat_id is primary key; name is hint only. Tool surface for agent-driven
identity resolution."
```

---

## Task 7: Hook `identity.harvest` vào `agent.handle_message`

**Files:**
- Modify: `src/agent.py` — sau khi parse kwargs, spawn harvest

- [ ] **Step 1: Thêm import**

Ở đầu [src/agent.py](src/agent.py):
```python
from src import identity
```

(Verify import existing imports nằm đâu — thêm chung block.)

- [ ] **Step 2: Spawn harvest task sau khi log INPUT**

Trong `handle_message`, ngay sau dòng `logger.info("%s >>> INPUT: ...")`:

```python
    # Fire-and-forget: harvest chat_ids observed in this update.
    # Index only — must not block or crash message flow.
    sender_dict = {"id": sender_id, "name": sender_name, "username": ""} if sender_id else None
    asyncio.create_task(
        identity.harvest(
            context_chat_id=chat_id,
            sender=sender_dict,
            mentions=mentions,
            reply_to=reply_to,
            new_members=new_members,
        )
    )
```

- [ ] **Step 3: Commit**

```bash
git add src/agent.py
git commit -m "feat(agent): spawn identity.harvest on every inbound message

Fire-and-forget upsert of sender/mentions/reply_to/new_members into
seen_contacts. Errors logged but never block message flow — index only."
```

---

## Task 8: `resolve_person` tool

**Files:**
- Modify: `src/tools/communication.py` — thêm tool mới

- [ ] **Step 1: Thêm hàm `resolve_person` cuối file**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/communication.py
git commit -m "feat(comm): add resolve_person tool

Returns all candidates matching query from Lark/bosses/memberships/seen_contacts.
Flags chat_id collisions and lark records missing Chat ID so agent can
propose merge/link. Agent decides action — tool exposes raw state."
```

---

## Task 9: Refactor `_find_person_chat_id` dùng `identity.resolve_candidates`

**Files:**
- Modify: `src/tools/communication.py:18-58`

- [ ] **Step 1: Thay nội dung hàm**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/communication.py
git commit -m "refactor(comm): _find_person_chat_id uses identity.resolve_candidates

Signature preserved; internals now search all identity sources
(lark_people → bosses → memberships → seen_contacts). send_dm/broadcast
benefit automatically — they can now DM people whose Lark record has no
Chat ID but whose chat_id exists in bosses/seen_contacts."
```

---

## Task 10: Expand `get_communication_log` — đọc cả `messages` table

**Files:**
- Modify: `src/tools/communication.py:184-221`

- [ ] **Step 1: Thay nội dung hàm**

```python
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

    # --- Section 1: outbound_messages ---
    outbound_rows = await db.get_outbound_log(
        boss_chat_id=ctx.boss_chat_id,
        to_chat_id=to_chat_id,
        trigger_type=log_type if log_type != "all" else None,
        limit=30,
    )

    # --- Section 2: messages table (DM thread) ---
    dm_rows: list[dict] = []
    if to_chat_id and to_chat_id > 0:
        _db = await db.get_db()
        async with _db.execute(
            """SELECT created_at, substr(content, 1, 200) AS content
               FROM messages
               WHERE chat_id = ? AND role = 'assistant'
               ORDER BY id DESC LIMIT 30""",
            (to_chat_id,),
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
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/communication.py
git commit -m "feat(comm): get_communication_log reads both outbound_messages and DM thread

Returns 2 labeled sections — boss-initiated cross-ws DMs (outbound_messages)
and direct bot-person DM threads (messages table). Fixes blind spot where
bot claimed 'never messaged X' while a DM thread existed.

When no chat_id is linked, lists candidate chat_ids from identity resolver
so agent can propose linking."
```

---

## Task 11: `link_contact_to_person` tool

**Files:**
- Modify: `src/tools/communication.py` — thêm cuối file

- [ ] **Step 1: Thêm hàm**

```python
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
```

- [ ] **Step 2: Verify `db.add_person` exists với signature đúng**

```bash
grep -n "async def add_person" src/db.py
```
Nếu signature khác, điều chỉnh call. Expected: `async def add_person(chat_id, boss_chat_id, person_type, name)`.

- [ ] **Step 3: Commit**

```bash
git add src/tools/communication.py
git commit -m "feat(comm): add link_contact_to_person tool

Explicit agent action to write Chat ID into a Lark People record that's
missing it. Refuses to overwrite existing different Chat ID ([CONFLICT]
response) — agent must surface to boss for confirmation. Also upserts
people_map for SQLite flows."
```

---

## Task 12: `list_unlinked_contacts` tool

**Files:**
- Modify: `src/tools/communication.py` — thêm cuối file

- [ ] **Step 1: Thêm hàm**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/communication.py
git commit -m "feat(comm): add list_unlinked_contacts tool

Lists chat_ids in seen_contacts that aren't yet linked to any current-workspace
Lark People record. Enables agent to review and propose linking."
```

---

## Task 13: `get_group_admins` tool

**Files:**
- Modify: `src/tools/communication.py` — thêm cuối file

- [ ] **Step 1: Thêm hàm**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add src/tools/communication.py
git commit -m "feat(comm): add get_group_admins tool

Returns admin list (chat_id + display name) of current group. Cached 10min
via telegram.get_chat_administrators. Another chat_id source for identity
resolution in group contexts."
```

---

## Task 14: Đăng ký 4 tool mới vào `TOOL_DEFINITIONS` + dispatch

**Files:**
- Modify: `src/tools/__init__.py`

- [ ] **Step 1: Thêm vào `TOOL_DEFINITIONS` (cạnh communication tools hiện tại)**

Tìm vị trí `"get_communication_log"` trong TOOL_DEFINITIONS (khoảng line 1010), chèn 4 entry sau dấu `},` đóng của `get_communication_log`:

```python
    {
        "type": "function",
        "function": {
            "name": "resolve_person",
            "description": (
                "Tra tất cả ứng viên người khớp query (tên/nickname/chat_id). "
                "Trả về nhiều nguồn: lark_people, bosses, memberships, seen_contacts — kèm source tag. "
                "GỌI TRƯỚC khi trả 'không tìm thấy X' hoặc 'X chưa có Chat ID' — "
                "có thể hệ thống đã biết chat_id của X qua nguồn khác."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Tên, nickname, hoặc chat_id số"},
                    "workspace_ids": {"type": "string", "description": "\"current\" (mặc định) | \"all\""},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "link_contact_to_person",
            "description": (
                "Gắn chat_id vào trường Chat ID của 1 Lark People record đang thiếu. "
                "Dùng khi xác định được seen_contacts/bosses chính là record Lark nào. "
                "Fails loud nếu record đã có Chat ID khác — phải hỏi sếp xác nhận trước khi overwrite."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {"type": "integer", "description": "Chat ID Telegram (số) cần gắn"},
                    "lark_record_id": {"type": "string", "description": "record_id của Lark People record đích"},
                    "workspace_ids": {"type": "string"},
                },
                "required": ["chat_id", "lark_record_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_unlinked_contacts",
            "description": (
                "Liệt kê chat_id bot đã thấy trong group/DM (Telegram) nhưng CHƯA gắn "
                "vào Lark People record nào của workspace hiện tại. Dùng khi sếp hỏi "
                "'ai trong group mà chưa add', hoặc khi cần proactively propose linking."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Xem trong N ngày qua (mặc định 30)"},
                    "limit": {"type": "integer", "description": "Tối đa N mục (mặc định 30)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_group_admins",
            "description": (
                "Trả danh sách admin của group hiện tại kèm chat_id. "
                "Chỉ chạy trong context group. Không list được non-admin members "
                "(Telegram API không cho phép)."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
```

- [ ] **Step 2: Thêm dispatch cases trong `_dispatch_tool`**

Tìm khối `# Communication tools` (khoảng line 1187), thêm ngay sau `case "get_communication_log":`:

```python
        case "resolve_person":
            return await communication.resolve_person(ctx, **args)
        case "link_contact_to_person":
            return await communication.link_contact_to_person(ctx, **args)
        case "list_unlinked_contacts":
            return await communication.list_unlinked_contacts(ctx, **args)
        case "get_group_admins":
            return await communication.get_group_admins(ctx, **args)
```

- [ ] **Step 3: Smoke import check**

```bash
cd /home/dat/2026/SMART_bot && python3 -c "
from src.tools import TOOL_DEFINITIONS
names = [t['function']['name'] for t in TOOL_DEFINITIONS]
for n in ['resolve_person','link_contact_to_person','list_unlinked_contacts','get_group_admins']:
    print(n, '✓' if n in names else '✗')
"
```
Expected: cả 4 đều ✓.

- [ ] **Step 4: Commit**

```bash
git add src/tools/__init__.py
git commit -m "feat(tools): register 4 new identity tools

resolve_person, link_contact_to_person, list_unlinked_contacts,
get_group_admins — descriptions prompt the agent to use them for
identity resolution and linking."
```

---

## Task 15: THINKING_MAP entries cho tool mới

**Files:**
- Modify: `src/agent.py` — THINKING_MAP (khoảng line 81-122)

- [ ] **Step 1: Thêm 4 entry**

Trong THINKING_MAP, thêm vào cuối (trước `}`):

```python
    "resolve_person": "Đang tra ứng viên người...",
    "link_contact_to_person": "Đang gắn Chat ID vào Lark...",
    "list_unlinked_contacts": "Đang xem chat_id chưa gắn...",
    "get_group_admins": "Đang xem admin group...",
```

- [ ] **Step 2: Commit**

```bash
git add src/agent.py
git commit -m "feat(agent): THINKING_MAP entries for identity tools"
```

---

## Task 16: SECRETARY_PROMPT — thêm Identity rules

**Files:**
- Modify: `src/agent.py:71-75` (cuối khối `## Cross-chat rules`)

- [ ] **Step 1: Thêm khối `## Identity rules` sau `## Cross-chat rules`**

Thay thế khối SECRETARY_PROMPT cuối (line 71-75) bằng:

```python
## Cross-chat rules
- Before answering "have you messaged X" or "did you remind X about Y": always call get_communication_log first.
- When the user asks about tasks/projects/workload across all their workspaces: pass workspace_ids="all".
- After a non-boss member marks a task complete (status → Hoàn thành or Huỷ): the update_task tool will auto-notify the boss and group. You do not need to do this manually.

## Identity rules
- chat_id là nguồn duy nhất xác định 1 người; tên có thể trùng/nhập nhằng/typo.
- Khi cần nhắn/nhắc/check ai đó mà Lark record thiếu Chat ID, GỌI resolve_person trước — hệ thống có thể đã biết chat_id qua bosses/memberships/seen_contacts.
- get_communication_log trả 2 section: outbound_messages (bot gửi qua send_dm/reminder) VÀ messages DM thread. Đọc cả 2 rồi mới kết luận.
- Khi resolve_person trả cùng 1 chat_id ở nhiều dòng khác source, và 1 dòng là lark_people chưa có Chat ID — đề xuất link_contact_to_person. Nếu boss chưa xác nhận rõ, hỏi confirm trước khi gắn.
- Nếu link_contact_to_person trả [CONFLICT] — KHÔNG tự overwrite; báo boss và chờ xác nhận.
- Trong group mà cần danh sách admin, gọi get_group_admins. Không list được non-admin (Telegram giới hạn).
"""
```

(Chú ý: đoạn trên phải close triple-quote bằng `"""` đúng cú pháp — verify sau khi paste.)

- [ ] **Step 2: Verify file load OK**

```bash
cd /home/dat/2026/SMART_bot && python3 -c "from src import agent; print('prompt len:', len(agent.SECRETARY_PROMPT))"
```
Expected: số > 2000.

- [ ] **Step 3: Commit**

```bash
git add src/agent.py
git commit -m "feat(agent): SECRETARY_PROMPT identity rules

Teaches agent:
- chat_id is authoritative, name is hint
- Call resolve_person before concluding 'X not found' or 'X has no Chat ID'
- Read both outbound_messages and DM thread sections
- Propose link_contact_to_person when same chat_id appears across sources
- On [CONFLICT], ask boss before overwriting"
```

---

## Task 17: Manual smoke test (thay cho unit test)

**Mục tiêu:** verify end-to-end theo 6 kịch bản trong spec, không dùng pytest.

- [ ] **Step 1: Restart bot service**

```bash
cd /home/dat/2026/SMART_bot && docker-compose restart
# hoặc tùy setup: pkill -f 'uvicorn\|main' && ... chạy lại
```

- [ ] **Step 2: Harvest via sender**

Trong 1 group test (đã onboard), user B (không phải boss) gửi 1 tin bình thường:
```
Alo thử 1 câu
```

Sau đó check:
```bash
cd /home/dat/2026/SMART_bot && python3 -c "
import sqlite3
con=sqlite3.connect('data/history.db'); con.row_factory=sqlite3.Row
for r in con.execute('SELECT * FROM seen_contacts ORDER BY last_seen_at DESC LIMIT 5'):
    print(dict(r))
"
```
Expected: có row với `chat_id` của user B, `seen_count >= 1`, `last_seen_chat` = group chat_id.

- [ ] **Step 3: Harvest via text_mention**

Boss tag user B trong group bằng cách gõ `@` rồi chọn B từ dropdown. Gửi:
```
@B @ceo_companion_bot test mention
```

Check `seen_contacts` — `seen_count` của chat_id B phải tăng.

- [ ] **Step 4: `resolve_person` cross-source**

Trong DM bot, boss nhắn:
```
@ceo_companion_bot resolve_person Linh
```

(Hoặc gọi tool qua chat natural: "em resolve giúp anh tên Linh xem có ai").

Expected: response liệt kê ít nhất 2 candidate — `lark_people` (Nguyên Linh, no chat_id) + `bosses` (Linh, chat_id=8638723771). Có dòng "Lưu ý" flag Lark record thiếu Chat ID.

- [ ] **Step 5: `get_communication_log` đọc DM thread**

Boss hỏi bot trong DM: "em đã nhắn Linh chưa?"

Expected: bot gọi `get_communication_log` (hoặc resolve_person trước), response có **Section 2 "DM thread"** với các tin bot đã DM cho chat_id 8638723771 (79 tin đã có trong `messages`). Bot không còn trả "Chưa nhắn" sai.

- [ ] **Step 6: `link_contact_to_person`**

Boss yêu cầu: "gắn chat_id 8638723771 vào record Nguyên Linh trong Lark".

Expected:
- Bot gọi `link_contact_to_person(chat_id=8638723771, lark_record_id="recvh0GHXujrFX")`.
- Response: `Đã gắn chat_id=8638723771 vào Lark record 'recvh0GHXujrFX' (Nguyên Linh).`
- Verify trên Lark UI: record Nguyên Linh có trường Chat ID = 8638723771.

Check DB:
```bash
python3 -c "
import sqlite3
con=sqlite3.connect('data/history.db'); con.row_factory=sqlite3.Row
for r in con.execute(\"SELECT * FROM people_map WHERE chat_id=8638723771\"):
    print(dict(r))
"
```
Expected: entry mới (boss_chat_id=5865065981, type=partner, name=Nguyên Linh).

- [ ] **Step 7: Regression check `send_dm`**

Boss DM bot: "nhắn riêng cho Nguyên Linh: test sau khi link".

Expected: `send_dm` resolve chat_id=8638723771, gửi thành công. Verify Linh nhận được tin.

- [ ] **Step 8: `list_unlinked_contacts`**

Boss hỏi: "liệt kê chat_id nào đã thấy mà chưa gắn Lark".

Expected: response có danh sách seen_contacts không có trong Lark People của AdaTech. Nguyên Linh **không còn** trong list (vừa gắn xong).

- [ ] **Step 9: `get_group_admins`**

Trong group test, boss tag bot: "liệt kê admin group này".

Expected: response có tên + chat_id admin.

- [ ] **Step 10: Final commit (nếu có fix phát sinh)**

Nếu bất kỳ step nào fail và cần chỉnh:
```bash
git add -u
git commit -m "fix: smoke-test adjustments"
```

Nếu tất cả pass, không cần commit thêm.

---

## Success Criteria Recap

- [ ] Telegram update có text_mention → row vào `seen_contacts` (< 5s sau tin).
- [ ] Sender bình thường (không tag) → `seen_contacts` cũng có row.
- [ ] `resolve_person("Linh")` trả >= 2 candidates kèm source tag.
- [ ] `get_communication_log("Linh")` khi chat_id resolve được → có Section 2 đọc từ `messages` table.
- [ ] `link_contact_to_person` ghi Chat ID vào Lark record; Lark UI confirm sau F5.
- [ ] `send_dm`/`broadcast` cũ không regression.
- [ ] `get_group_admins` trong group trả đúng admin list.
- [ ] Bot không còn trả "chưa nhắn X" sai khi X có DM thread.
