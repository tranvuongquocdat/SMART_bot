# Person Identity & Chat-ID Harvesting — Design Spec

> **For agentic workers:** Use superpowers:executing-plans to implement this plan.

**Goal:** Khai thác tối đa dữ liệu identity mà Telegram đã đưa sẵn (entities, reply, new_chat_members, admin list, sender) để bot tự dựng pool chat_id và resolve người được hỏi — thay vì mù khi Lark record thiếu Chat ID. Mọi tool expose state cho agent tự tư duy, không hardcode flow.

**Date:** 2026-04-17

---

## Problem

1. Boss hỏi "đã nhắn Nguyên Linh chưa" → bot trả sai vì Lark record "Nguyên Linh" không có Chat ID, trong khi hệ thống **đã biết** chat_id `8638723771` qua `bosses` table (cùng 1 người).
2. `message.entities[].user.id` (text_mention) không được parse → mất chat_id free.
3. `_find_person_chat_id` ([communication.py:18-58](../../../src/tools/communication.py#L18-L58)) chỉ search Lark People current workspace — không fallback `bosses`/`memberships`.
4. `get_communication_log` chỉ đọc `outbound_messages` — bỏ qua `messages` (DM thread thật bot ↔ person).
5. Khi chat_id không có, tool trả lời mơ hồ; agent không biết phải làm gì tiếp.

---

## Core Principle

- **`chat_id` = primary key** (Telegram guarantee unique).
- **`name` = hint** (ambiguous, typo, nickname).
- Mọi quyết định linking ưu tiên match chat_id; name chỉ dùng tìm candidates.
- **Tool expose raw state; agent tự interpret + chọn action.** Không auto-mutate user data, không hardcode flow confirm.

---

## Architecture — 5 Layer

```
Telegram update
    │
    ▼
[Layer 1] Parse entities/reply/new_members  ──► callback kwargs
    │
    ▼
[Layer 2] Harvest contacts (fire-and-forget)  ──► seen_contacts table
    │
    ▼
Agent handling (existing)
    │
    ├─► [Layer 3] resolve_person(query) tool      ──► returns candidates
    │
    ├─► [Layer 4] get_communication_log (expanded) ──► outbound + messages
    │
    └─► [Layer 5] link_contact_to_person tool      ──► explicit upsert to Lark
```

---

## Layer 1 — Telegram Harvest Parsing

**File:** [src/services/telegram.py](../../../src/services/telegram.py) — hàm `start_polling` (line 56-115).

**Parse thêm từ mỗi update:**

| Field | Extract |
|---|---|
| `message.from` | `{id, first_name, last_name, username}` → `sender` (đã có `sender_id`) |
| `message.entities[]` where `type="text_mention"` | `[{id, first_name, username}]` → `mentions` |
| `message.entities[]` where `type="mention"` | `[{username}]` (chỉ text `@xxx`, không có user_id) → `username_mentions` |
| `message.reply_to_message.from` | `{id, first_name, username}` → `reply_to` |
| `message.new_chat_members[]` | `[{id, first_name, username}]` → `new_members` |

**Callback signature mở rộng (backward-compatible qua kwargs):**

```python
await on_message(
    text, chat_id, sender_id, is_group, bot_mentioned, group_name,
    # new:
    sender_name: str = "",
    mentions: list[dict] = None,          # [{id, name, username}]
    username_mentions: list[str] = None,  # ["linh_dev", ...]
    reply_to: dict | None = None,         # {id, name, username}
    new_members: list[dict] = None,
)
```

Caller [main.py:41](../../../src/main.py#L41) truyền `agent.handle_message` — `agent.handle_message` nhận thêm kwargs với default.

**Admin list:** không đưa vào callback — quá nặng cho mỗi message. Thay vào đó expose tool `get_group_admins(chat_id)` để agent gọi khi cần (cache in-memory 10 phút).

---

## Layer 2 — Contact Harvest (Passive)

**File mới:** `src/identity.py`.

**Hook point:** trong `agent.handle_message`, sau khi resolve context, spawn:

```python
asyncio.create_task(identity.harvest(chat_id, sender, mentions, reply_to, new_members))
```

**Wrap try/except + log warning** — fire-and-forget ở đây chấp nhận được vì là index phụ, không phải data chính.

**Logic `harvest`:**

1. Gom tất cả `(user_id, display_name, username)` từ sender + mentions + reply_to + new_members.
2. Với mỗi contact, upsert vào bảng `seen_contacts`:

```sql
CREATE TABLE IF NOT EXISTS seen_contacts (
    chat_id          INTEGER PRIMARY KEY,
    display_name     TEXT,
    username         TEXT,
    first_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_chat   INTEGER,
    seen_count       INTEGER DEFAULT 1
);
```

3. **Không mutate Lark**. Không call agent. Chỉ ghi DB.

Bảng `seen_contacts` là **append-only pool** mà agent có thể query sau.

---

## Layer 3 — Identity Resolution Tool (Replaces Hidden Fallback)

**File:** [src/tools/communication.py](../../../src/tools/communication.py).

### New tool: `resolve_person(query, workspace_ids="current")`

Trả **all candidates** thay vì chọn 1, cho agent tự quyết.

```python
async def resolve_person(
    ctx: ChatContext,
    query: str,               # name | nickname | chat_id (as string)
    workspace_ids: str = "current",
) -> str:
    """
    Trả tất cả ứng viên người tên/nickname/chat_id khớp query.
    Mỗi ứng viên có source tag để agent phân biệt:
      - lark_people (current/other workspace) — có thể có record_id
      - bosses      (là boss 1 workspace)
      - memberships (thành viên đã onboard)
      - seen_contacts (Telegram đã thấy chưa link Lark)

    Dùng khi cần DM/nhắc ai đó mà tên ambiguous, hoặc cross-check
    1 chat_id đã biết thuộc về ai trong hệ thống.
    """
```

**Return format (human-readable, chứa đủ info để agent reason):**

```
Kết quả resolve "Linh":
1. chat_id=8638723771 | name="Linh" | source=bosses | workspace="MyGyms" | confidence=exact_name
2. chat_id=null       | name="Nguyên Linh" | source=lark_people[AdaTech] | record_id=recvh0GHXujrFX | confidence=partial_name | note="Có thể gọi là Linh" (từ Ghi chú)
3. chat_id=8638723771 | name="Linh" | source=seen_contacts | last_seen=2026-04-17 02:09 | username="linh_dev"

=> Lưu ý: 1 và 3 cùng chat_id → cùng 1 người. Record 2 chưa có Chat ID.
```

### `_find_person_chat_id` refactor (keep signature)

Giữ signature cũ để không break `send_dm`/`broadcast`/`get_communication_log`. Internals đổi:

```python
async def _find_person_chat_id(ctx, name, workspace_ids="current"):
    candidates = await identity.resolve_candidates(ctx, name, workspace_ids)
    linked = [c for c in candidates if c["chat_id"]]
    if not linked:
        return None, name, ""
    # Disambiguation rule as before (prefer current workspace in group)
    if ctx.is_group and len(linked) > 1:
        preferred = [c for c in linked if c.get("workspace_boss_id") == ctx.boss_chat_id]
        if preferred:
            linked = preferred
    best = linked[0]
    return best["chat_id"], best["name"], best.get("workspace_name", "")
```

### Source priority in `identity.resolve_candidates` (internal)

1. Lark People current workspace (match name/nickname)
2. Lark People other workspaces user thuộc về
3. `bosses` table match name/nickname
4. `memberships` table match name
5. `seen_contacts` match display_name/username

Dedup theo chat_id (giữ entry có record_id Lark trước).

**Candidate dict shape** (internal, dùng bởi `_find_person_chat_id`):

```python
{
    "chat_id": int | None,
    "name": str,
    "source": "lark_people" | "bosses" | "memberships" | "seen_contacts",
    "record_id": str | None,        # chỉ có khi source=lark_people
    "workspace_name": str | None,   # chỉ có khi source=lark_people
    "workspace_boss_id": int | None,
    "confidence": "exact_name" | "partial_name" | "nickname_match" | "exact_id",
}
```

`resolve_person` tool (user-facing) format lại thành text có đánh số + note khi có cùng chat_id.

---

## Layer 4 — Communication Log Expansion

**File:** [src/tools/communication.py](../../../src/tools/communication.py) — `get_communication_log`.

### Thay đổi

1. Resolve chat_id qua Layer 3 (`identity.resolve_candidates`).
2. Nếu có chat_id, query **2 nguồn**:
   - `outbound_messages WHERE boss_chat_id=? AND to_chat_id=?` (đã có)
   - `messages WHERE chat_id=? AND role='assistant'` (DM thread; `chat_id > 0` = DM)
3. Không merge/dedup — trả **2 section** riêng với label.
4. Nếu không có chat_id → trả raw state + resolve candidates:

```
Chưa có Chat ID cho "Nguyên Linh". Ứng viên gần đúng:
  - chat_id=8638723771 "Linh" (source=bosses)
Có thể cùng 1 người — gọi link_contact_to_person để gắn.
```

**Không hardcode message "X cần /start bot"** — để agent tự compose dựa trên state.

---

## Layer 5 — Explicit Linking Tool

**File:** [src/tools/communication.py](../../../src/tools/communication.py) hoặc `src/tools/people.py`.

### New tool: `link_contact_to_person(chat_id, lark_record_id, workspace_ids="current")`

```python
async def link_contact_to_person(
    ctx: ChatContext,
    chat_id: int,
    lark_record_id: str,
    workspace_ids: str = "current",
) -> str:
    """
    Gắn chat_id vào Lark People record (update field "Chat ID").
    Dùng khi agent xác định 1 người trong seen_contacts/bosses chính là
    1 record Lark đang thiếu Chat ID. Explicit action — agent quyết định, không tự động.

    Side effects: cũng tạo entry trong people_map (boss_chat_id, chat_id, name, type=member/partner).
    """
```

**Trả về:**
- Success: `"Đã link chat_id=X vào Lark record Y (name=Z)."`
- Fail (record đã có Chat ID khác): `"[CONFLICT] Record Y đã có Chat ID W khác X. Confirm merge hoặc chọn record khác."` → agent quyết định overwrite/skip.

### New tool: `list_unlinked_contacts(limit=30)`

```python
async def list_unlinked_contacts(ctx: ChatContext, limit: int = 30) -> str:
    """
    Liệt kê chat_id bot đã thấy trong group/DM nhưng chưa gắn với Lark People nào
    (của boss hiện tại). Dùng để agent review + link tay khi cần.
    """
```

Query: `seen_contacts LEFT JOIN lark_people WHERE lark_record_id IS NULL AND last_seen_at in last 30 days`.

---

## TOOL_DEFINITIONS Update

File: [src/tools/__init__.py](../../../src/tools/__init__.py).

Thêm 3 tool mới vào `TOOL_DEFINITIONS` + `_dispatch_tool`:
- `resolve_person`
- `link_contact_to_person`
- `list_unlinked_contacts`

Thêm 1 tool nhỏ:
- `get_group_admins` (cho Layer 1 admin discovery)

Mô tả tool **fat, nói rõ khi nào agent nên gọi** (theo pattern CROSS_CHAT_RULES có sẵn ở SECRETARY_PROMPT).

---

## SECRETARY_PROMPT Addition

File: [src/agent.py](../../../src/agent.py).

Thêm vào SECRETARY_PROMPT phần `## Identity rules`:

```
- chat_id là nguồn xác định 1 người duy nhất; tên có thể trùng/nhập nhằng.
- Trước khi trả "chưa nhắn X" hoặc "không tìm thấy X" khi X thiếu Chat ID, LUÔN gọi resolve_person để xem có nguồn nào khác trong hệ thống đã biết chat_id chưa (bosses, seen_contacts).
- Khi thấy 1 người trong seen_contacts chắc chắn là record Lark đang thiếu Chat ID, chủ động gọi link_contact_to_person. Nếu chưa chắc, hỏi boss xác nhận trước.
- get_communication_log trả 2 section (outbound_messages + messages DM thread); đọc cả hai trước khi kết luận.
- Nếu boss hỏi về 1 người mà resolve_person trả nhiều candidates cùng chat_id nhưng khác record Lark, đề xuất merge/link cho boss.
```

---

## File Map

| File | Thay đổi | Kiểu |
|---|---|---|
| `src/services/telegram.py` | Parse entities/reply/new_chat_members trong `start_polling`; mở rộng callback kwargs; thêm `get_chat_administrators` helper | Mở rộng |
| `src/agent.py` | `handle_message` nhận kwargs mới; spawn `identity.harvest`; thêm identity rules vào SECRETARY_PROMPT; THINKING_MAP entries cho tool mới | Mở rộng |
| `src/identity.py` | Module mới: `harvest()`, `resolve_candidates()` | Mới |
| `src/tools/communication.py` | `_find_person_chat_id` gọi `identity.resolve_candidates`; `get_communication_log` đọc thêm `messages`; thêm `resolve_person`, `link_contact_to_person`, `list_unlinked_contacts`, `get_group_admins` | Mở rộng |
| `src/tools/__init__.py` | `TOOL_DEFINITIONS` + `_dispatch_tool` cho 4 tool mới | Mở rộng |
| `src/db.py` | Schema `seen_contacts`; helpers `upsert_seen_contact`, `get_seen_contact`, `list_unlinked_seen_contacts` | Mở rộng (additive) |

**Không đụng:** `src/context.py`, `src/scheduler.py`, `src/onboarding.py`, `src/group_onboarding.py`, `src/tools/tasks.py`, onboarding tests.

---

## DB Schema

```sql
CREATE TABLE IF NOT EXISTS seen_contacts (
    chat_id          INTEGER PRIMARY KEY,
    display_name     TEXT,
    username         TEXT,
    first_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_chat   INTEGER,       -- chat_id group/DM nơi thấy lần cuối
    seen_count       INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_seen_contacts_name
    ON seen_contacts (display_name);
CREATE INDEX IF NOT EXISTS idx_seen_contacts_username
    ON seen_contacts (username);
```

Additive only. Không migrate existing data.

---

## Prerequisite Fix

**[src/services/lark.py](../../../src/services/lark.py) `update_record`** hiện không check `body.get("code") != 0` — Lark business error (field sai, permission, quota) sẽ silent succeed. Layer 5 `link_contact_to_person` yêu cầu behavior "fail loud" nên cần fix 1 dòng trước:

```python
async def update_record(...):
    resp = await _client.put(...)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise Exception(f"Lark error: {body.get('code')} - {body.get('msg')}")
    return body["data"]["record"]
```

Tương tự cho `search_records` (nếu time cho phép) — không bắt buộc trong scope spec này nhưng là điểm cùng pattern, nên làm chung.

---

## Edge Cases & Error Handling

| Trường hợp | Xử lý |
|---|---|
| Telegram update không có `entities` | `mentions=[]`, `reply_to=None` — OK |
| `text_mention` user đã bị Telegram delete | `id` vẫn còn; username có thể empty — lưu như bình thường |
| Harvest DB error | Log warning; không raise; message flow vẫn chạy |
| `resolve_person` query = chat_id số | Direct lookup seen_contacts + bosses |
| 2 record Lark khác name cùng chat_id | `resolve_person` trả cả 2 với note "cùng chat_id → có thể cùng người"; agent quyết định merge |
| `link_contact_to_person` với record Lark đã có Chat ID khác | Return `[CONFLICT]` → agent hỏi boss |
| Lark update fail khi link | Raise + log; không fake success (tuân nguyên tắc "Lark là source of truth") |
| Admin list Telegram API fail | Return empty list + log; không crash |

---

## Non-Goals

- **Không** discover thành viên cũ chưa bao giờ chat/tag (Telegram API không cho).
- **Không** resolve `@username` text mention thành user_id (cần `resolveUsername` — ngoài scope).
- **Không** refactor onboarding flow.
- **Không** retro-backfill Chat ID cho Lark records cũ (tool mới cho phép boss/agent làm manual sau).
- **Không** merge/dedup Lark records tự động — agent đề xuất, boss confirm.
- **Không** đổi schema existing tables (`bosses`, `memberships`, `people_map`, `outbound_messages`).

---

## Manual Smoke Test (user yêu cầu skip unit test lần này)

Sau khi deploy, test thật theo kịch bản:

1. **Harvest entities**: trong 1 group đã onboard, tag 1 user bằng text_mention (UI @ picker) → `SELECT * FROM seen_contacts` phải có row với đúng chat_id.
2. **Harvest sender**: 1 user chưa có Lark Chat ID gửi 1 tin vào group → `seen_contacts` phải upsert.
3. **resolve_person**: DM bot `resolve_person("Linh")` → response phải liệt kê candidates từ `bosses` + `lark_people` + `seen_contacts`, kèm source tag.
4. **get_communication_log cho người có DM thread**: hỏi bot "em đã nhắn Linh chưa" trong context Đạt → bot phải nhắc DM thread (messages table) thay vì "chưa nhắn".
5. **link_contact_to_person**: bảo bot "gắn chat_id 8638723771 vào record Nguyên Linh" → verify Lark record có Chat ID. Refresh Lark UI confirm.
6. **Không regression**: chạy lại flow `send_dm` cũ (DM ai đó có Chat ID) → phải vẫn hoạt động.

---

## Success Criteria

- Sau khi 1 user tag `@X` hoặc gửi 1 tin trong group đã onboard, `chat_id` của X xuất hiện trong `seen_contacts`.
- Boss hỏi "đã nhắn X chưa" với X thiếu Lark Chat ID nhưng có trong `bosses`/`seen_contacts` → bot trả rõ: chat_id + nguồn + có hay không log DM.
- Agent có thể chủ động link Chat ID từ `seen_contacts` vào Lark record qua `link_contact_to_person`.
- Không break bất kỳ tool CRUD hiện tại; `send_dm`/`broadcast` tiếp tục hoạt động.
