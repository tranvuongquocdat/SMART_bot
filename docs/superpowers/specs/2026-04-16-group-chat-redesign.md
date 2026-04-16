# AI Secretary — Group Chat Redesign Spec

**Date:** 2026-04-16  
**Status:** Approved  
**Scope:** Group onboarding, group context enrichment, group tools, permission model, approval flow, scheduled review, Telegram group management

---

## Problems Being Fixed

1. **Wrong onboarding path** — bot tagged in unregistered group falls into personal onboarding (asks name, company, role). Should run a dedicated group onboarding flow.
2. **No group context in prompt** — system prompt is identical for personal and group. Bot doesn't know group name, linked project, active topic, or recent participants.
3. **Group notes never written** — schema exists (`notes` table type="group") but no tool writes to it.
4. **Notification routing is personal-only** — scheduler DMseveryone. Group deadlines / team briefs never go to the group chat.
5. **No group management tools** — bot can't invite members, rename group, pin messages, etc.
6. **Approval flow is DM-only** — member updates in group context have no feedback loop back to the group.
7. **Permission model undefined for groups** — "permissions follow the person who tagged" is too vague; sensitive info could leak in group reply.

---

## Design Philosophy

Same as the secretary redesign: **trust the agent with better context and better tools.** No hardcoded group routing. No keyword matching. System prompt gets a group-specific section when `is_group=True`. Tools handle the group-specific operations. Agent reasons about what to do publicly vs. privately.

---

## Architecture

### New / Changed Files

| File | Action | Responsibility |
|---|---|---|
| `src/group_onboarding.py` | **New** | Group registration flow (workspace → project → admin check → introduce) |
| `src/context_builder.py` | Modify | Add group context block when `is_group=True` |
| `src/agent.py` | Modify | Intercept unregistered group before personal onboarding; inject group context into prompt |
| `src/tools/group.py` | **New** | `summarize_group_conversation`, `update_group_note`, `broadcast_to_group`, `manage_group` |
| `src/services/telegram.py` | Modify | Add group management API wrappers |
| `src/tools/__init__.py` | Modify | Register new group tools |
| `src/db.py` | Modify | `group_map` add `project_id`; `scheduled_reviews` add `group_chat_id` |
| `src/scheduler.py` | Modify | Route group_brief to group chat instead of boss DM |

---

## Group Onboarding Flow

Triggered when: `is_group=True` AND group not in `group_map` AND bot is mentioned.

```
Step 1 — Check admin rights
  Bot calls getChatMember(bot_id) to check own permissions
  If NOT admin:
    Send guidance in group: "Để em hoạt động đầy đủ, nhờ admin promote em lên làm admin nhóm:
    Settings → Administrators → Add Administrator → chọn @bot → bật quyền cần thiết"
    Stop. Wait for next message that triggers the check again.
  If admin → proceed to Step 2

Step 2 — Link workspace
  Bot sends: list all registered workspaces (from db.get_all_bosses())
  "Nhóm này thuộc workspace nào?"
  User picks workspace (by number or name, LLM classifies)

Step 3 — Link project
  Bot fetches projects of chosen workspace from Lark
  "Nhóm này phục vụ dự án nào?"
  User picks project (or "không thuộc dự án cụ thể")

Step 4 — Confirm and register
  db.add_group(group_chat_id, boss_chat_id, group_name, project_id)
  Write initial group note: group name, linked project, setup date

Step 5 — Introduce bot in group
  AI-generated introduction tailored to group context:
  "Xin chào nhóm [name]! Em là thư ký AI của [company]...
   Các bạn chưa đăng ký với em thì nhắn /start để em nhận ra nhé."
```

### Admin Check (ongoing)
Bot checks admin status before executing any group management action. If no longer admin, notifies and asks to be re-promoted.

---

## Group Context Enrichment

`context_builder.py` adds a `group_context` block when `is_group=True`:

```python
"group_context": {
    "group_name": str,
    "project": {"name": str, "status": str} | None,   # from group_map.project_id → Lark
    "group_note": str | None,                           # db.get_note(boss_id, "group", chat_id)
    "recent_participants": [str, ...],                  # distinct sender names, last 15 messages
    "active_topic": str,                                # LLM mini-call on last 10 messages
}
```

**`active_topic` — LLM mini-call:**
```python
async def _summarize_topic(messages: list[str]) -> str:
    """1-sentence summary of what the group is currently discussing."""
    # System: "Summarize in 1 sentence what topic this group conversation is about."
    # User: last 10 messages joined
    # Returns: e.g. "Đang bàn về deadline thiết kế logo dự án X"
```

### Group Section in System Prompt

Added to `SECRETARY_PROMPT` when `is_group=True`:

```
## Group context
Nhóm: {group_name} | Project: {project_name}
Đang bàn: {active_topic}
Tham gia gần đây: {recent_participants}
Ghi chú nhóm: {group_note}
```

---

## Permission Model

**Principle injected in system prompt (not hardcoded):**

```
## Group permissions
Trong nhóm, ưu tiên reply công khai — cả team cần biết tiến độ, deadline, workload.
Chuyển sang DM khi thông tin mang tính cá nhân hoặc nhạy cảm (đánh giá cá nhân,
ghi chú riêng tư, kết quả approval). Khi gửi DM thay vì reply nhóm, thông báo
trong nhóm rằng đã gửi riêng.

Member trong nhóm được xem: tất cả task của team, workload, tiến độ project.
Member KHÔNG thể sửa task người khác mà không qua approval.
Chỉ boss mới được thực hiện: kick member, đổi quyền, xóa task.
```

Agent reasons case-by-case. No hardcoded if/else.

---

## Approval Flow in Group

```
Member tags bot in group: "em xong task thiết kế logo rồi"
  → Bot replies in group: "Em ghi nhận. Đang gửi cho [boss] duyệt."
  → DM boss: "[Nhóm ABC] Bách báo xong task 'Thiết kế logo'. Duyệt không anh?"
  → Boss replies in DM (or tags bot in group to approve)
  → Bot broadcasts result in group: "Task 'Thiết kế logo' đã được duyệt xong ✓"
```

Boss can approve from either DM or group — Secretary recognizes both contexts.

---

## New Tools — `src/tools/group.py`

### `summarize_group_conversation(ctx, n_messages=20)`
Reads last N messages from the group, returns LLM summary including:
- Main topic discussed
- Decisions made
- Action items not yet assigned as tasks

Useful when: "tóm tắt cuộc họp vừa rồi", or bot auto-summarizes at end of meeting.

### `update_group_note(ctx, content)`
Appends or overwrites note for this group (`notes` table, type="group", ref_id=chat_id).
Used to record group rules, recurring context, decisions.

### `broadcast_to_group(ctx, message)`
Sends a message to the group chat (vs DM).
Used for: team announcements, deadline broadcasts, approval results.

### `manage_group(ctx, action, **kwargs)`

Single tool covering all Telegram group management actions.
Agent passes `action` string; tool dispatches to the right Telegram API call.
Requires bot to be admin.

| action | kwargs | What it does |
|---|---|---|
| `invite` | `name: str` | Find person in People table → try `addChatMember`; fallback to invite link if never DM'd bot |
| `rename` | `title: str` | `setChatTitle` |
| `pin` | `message_id: int \| None` | `pinChatMessage` — nếu `None`, pin tin nhắn bot vừa gửi gần nhất |
| `unpin` | | `unpinAllChatMessages` |
| `kick` | `name: str` | `banChatMember` + immediate unban (removes from group) |
| `set_description` | `text: str` | `setChatDescription` |
| `invite_link` | | `createChatInviteLink(member_limit=1, expire_hours=24)` |

**Invite with graceful fallback:**
```python
async def _invite_member(ctx, name):
    person = search_people_table(name)  # finds chat_id
    if person:
        try:
            await telegram.add_chat_member(ctx.chat_id, person["chat_id"])
            return f"Đã mời {name} vào nhóm."
        except TelegramError:
            pass  # person hasn't DM'd bot
    # Fallback: generate single-use 24h link
    link = await telegram.create_invite_link(ctx.chat_id, member_limit=1, expire_hours=24)
    return f"{name} chưa nhắn bot lần nào. Đây là link mời (dùng 1 lần, hết hạn 24h): {link}"
```

---

## Group Scheduled Review

`scheduled_reviews` table gets a new nullable `group_chat_id` column.

When `group_chat_id` is set → scheduler sends to group instead of boss DM.

New review type: **`group_brief`**

Default content:
- Deadline hôm nay của team
- Ai đang quá tải
- Task mới được giao từ hôm qua
- Blockers cần chú ý

Boss configures via chat: *"thêm lịch briefing nhóm lúc 8:30"* → Secretary creates a `group_brief` scheduled review with `group_chat_id` set.

---

## Member Discovery

Bot cannot fetch Telegram group member list via API reliably. Discovery is self-service:

1. After group onboarding, bot sends: *"Các bạn chưa đăng ký với em, nhắn /start để em nhận ra trong nhóm nhé."*
2. Members DM `/start` → personal onboarding → linked to workspace → bot now knows their `chat_id` → future group interactions work fully.
3. Bot tracks `recent_participants` from messages table — anyone who has spoken in the group and registered is known.

---

## Telegram Service Additions — `src/services/telegram.py`

New wrapper functions:

```python
async def get_chat_member(chat_id: int, user_id: int) -> dict
async def add_chat_member(chat_id: int, user_id: int) -> bool
async def set_chat_title(chat_id: int, title: str) -> bool
async def set_chat_description(chat_id: int, description: str) -> bool
async def pin_chat_message(chat_id: int, message_id: int) -> bool
async def unpin_all_chat_messages(chat_id: int) -> bool
async def ban_chat_member(chat_id: int, user_id: int) -> bool
async def unban_chat_member(chat_id: int, user_id: int) -> bool
async def create_invite_link(chat_id: int, member_limit: int = 1, expire_hours: int = 24) -> str
```

All use the existing `httpx` session in `telegram.py`. Follow same error handling pattern.

---

## Data Model Changes

```sql
-- group_map: add project_id
ALTER TABLE group_map ADD COLUMN project_id TEXT DEFAULT NULL;
-- project_id = Lark record_id of the linked project

-- scheduled_reviews: add group_chat_id
ALTER TABLE scheduled_reviews ADD COLUMN group_chat_id INTEGER DEFAULT NULL;
-- NULL = send to boss DM (current behavior)
-- Set = send to this group chat
```

---

## What Is NOT Changing

- Personal onboarding — unchanged
- DM flows — unchanged
- Lark Base schema — unchanged
- Approval logic core — unchanged (just adds group notification layer)
- Advisor agent — unchanged
- Multi-workspace tools — unchanged

---

## Known Limitations

- Bot must be admin to use group management features. If demoted, management tools return an error and prompt re-promotion.
- Members who never DM'd bot can only be invited via link (Telegram API limitation).
- `active_topic` LLM mini-call adds ~300ms + ~200 tokens per group message that mentions bot — acceptable at current scale.
- Telegram does not expose full group member list to bots. Member discovery relies on self-service /start.
