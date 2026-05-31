[← Index](./README.md)

# §6. Agent layer

## 6.1 Operations & Operation Router

3 op chính (entry point từ inbound event) + 1 op nền (scheduler):

| Operation | Trigger | Mục tiêu | Output |
|---|---|---|---|
| **GroupNoteUpdater** | Debounce/threshold ([§4.3](./04-group-note.md#43-vòng-đời-update)) | Rebuild markdown của group_note | UPDATE group_notes |
| **InGroupResponder** | `@bot` mention trong group | Trả lời tại group | Outbound message |
| **DMResponder** | Sếp DM cho bot | Trả lời sếp riêng | Outbound DM |
| **ReminderFirer** (nền) | Scheduler tick khi `due_at` đến hạn ([§13](./13-reminders-tasks.md)) | Gửi nhắc đúng nhóm gốc / DM sếp | Outbound message |

### Operation Router

```python
def route(event: InboundEvent) -> Operation:
    if event.chat_type == "dm" and event.sender_is_boss:
        return Operation.DM_RESPONDER
    if event.chat_type == "group":
        if event.mentions_bot:
            return Operation.IN_GROUP_RESPONDER
        return Operation.NOTE_UPDATER_SCHEDULE   # no reply, queue update only
    return Operation.DROP
```

Operation Router không phải LLM — đây là code rule. LLM intent classify
chỉ chạy **bên trong** op (vd DMResponder phân biệt "set reminder" vs
"Q&A" qua tool call).

## 6.2 Single agent vs multi-agent

Đây là câu hỏi anh đặt rõ. Em phân tích:

**Multi-agent (kiểu LangGraph)**: 1 op = nhiều LLM call cho nhiều
"agent" specialised (vd ResearcherAgent → SearcherAgent → WriterAgent).
Pro: phân vai bài bản. Con: latency tăng 3–10x, debug khó, prompt phình.

**Single agent per op**: mỗi op = 1 LLM call có tool. Tool dispatcher chạy
tool, LLM tiếp tục. Simple, debug dễ, latency thấp.

Em recommend **single agent per op** vì:
- Op của mình không phức tạp đến mức cần phân vai (NoteUpdater = "rebuild
  markdown từ input"; Responder = "trả lời câu hỏi với tool")
- Multi-agent thường wins khi task có planning phức tạp nhiều bước —
  ở đây không có.
- Cost & latency là constraint thực tế.

Nhưng giữa các op vẫn "đa agent" theo nghĩa **3 op = 3
prompt/persona/tier khác nhau**:
- **NoteUpdater**: prompt "biên tập markdown", smart tier, tool tối
  thiểu (chỉ `edit_note`)
- **InGroupResponder**: prompt "thư ký trong group", smart hoặc fast tuỳ
  feature (xem [§7.3](./07-llm-abstraction.md#73-router--feature-routing)),
  full core tool + plugin tool
- **DMResponder**: prompt "thư ký riêng cho sếp", smart, full tool

**Quyết định:** single-agent per op, 3 op tách biệt. Multi-agent giữ
làm option Phase 2 nếu trải nghiệm thật cho thấy task quá phức tạp.

## 6.3 Tool calling

Follow chuẩn OpenAI function calling. Tool đăng ký vào dispatcher:

```python
@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict             # JSON Schema
    handler: Callable[[dict, BossContext], Awaitable[ToolResult]]
```

**Core tools (always available):**

| Tool | Mô tả |
|---|---|
| `search_history(query, group?, days?)` | Hybrid FTS + vector retrieval trên messages |
| `read_group_note(group_id)` | Trả về note hiện tại |
| `refresh_group_note(group_id)` | Trigger NoteUpdater on-demand |
| `edit_group_note(group_id, section, new_content)` | Sửa 1 section (bot dùng cho DMResponder) |
| `list_action_items(group_id?, status?)` | List task từ section "Việc đang mở" |
| `mark_action_item(item_id, status)` | Đánh dấu done/cancel |
| `set_reminder(text, due_at, scope, target?)` | Đặt reminder ([§13](./13-reminders-tasks.md)). `scope ∈ {group, dm}`, `target` = chat_id hoặc auto. |
| `list_reminders(status?, group?)` | List reminder pending/done của sếp |
| `cancel_reminder(reminder_id)` | Huỷ reminder |
| `pin_message(message_id, note?)` | Pin 1 tin nhắn vào section "Đã pin" của group note. Sếp `@bot pin tin này` (reply tin cần pin). |
| `unpin_message(pin_id)` | Bỏ pin |
| `find_exact_quote(fragment, group?)` | Tìm chính xác quote từ history; trả về `{author, ts, full_text, context_before, context_after}` |
| `update_boss_profile(key, value)` | Ghi vào `users.boss_profile` (memory tier core, [§6.4](#64-context-window--memory-tier)). Vd: "cứ gọi tôi là Đạt nhé" → key="preferred_name" |
| `list_groups()` | Liệt kê group sếp đang link |
| `current_time()` | Thời gian hiện tại theo TZ sếp |
| `fetch_url(url)` | Fetch + extract URL/YouTube/file (port legacy, [§5.4](./05-capture-flow-data-model.md#54-media-ingest)) |

**Plugin tools** (load động per-boss, xem [§8](./08-plugin-architecture.md)).

### `pins` schema

```sql
pins (
  id              BIGSERIAL PRIMARY KEY,
  boss_id         INTEGER NOT NULL REFERENCES users(id),
  group_note_id   BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
  message_id      BIGINT NOT NULL REFERENCES messages(id),
  note            TEXT,                           -- ghi chú lý do pin (optional)
  pinned_by       INTEGER NOT NULL REFERENCES users(id),
  pinned_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (group_note_id, message_id)
);
CREATE INDEX idx_pins_group ON pins(group_note_id);
```

NoteUpdater render section `Đã pin` (template `behavior='manual_pin'`):
list bullets từ `pins` join `messages`, format `{sender_name}: "{text}" ({ts}) — note: {note}`.
LLM không sửa section này.

### `find_exact_quote` impl

Wrap FTS chính xác (không qua vector):

```python
async def find_exact_quote(fragment: str, boss_id: int, group_id: int | None = None):
    # 1. FTS exact phrase
    matches = await messages_repo.fts_search(fragment, boss_id, group_id, exact=True, limit=5)
    # 2. Cho mỗi match, load ±3 message context
    return [
        {
            "author": m.sender_name, "ts": m.ts,
            "full_text": m.text,
            "context_before": before, "context_after": after,
        }
        for m in matches
    ]
```

Tool này khác `search_history` (hybrid retrieval) ở chỗ: trả nguyên văn,
có context xung quanh — phù hợp khi sếp hỏi "ai nói câu A đó?".

**Tool calling loop:**

```python
async def agent_loop(op_ctx, max_depth=5):
    messages = build_initial(op_ctx)
    for step in range(max_depth):
        resp = await llm.chat(messages, tools=tools_for(op_ctx))
        if not resp.tool_calls:
            return resp.content
        for call in resp.tool_calls:
            result = await dispatcher.call(call, op_ctx)
            messages.append(tool_message(call.id, result))
    log.warn("max depth reached")
    return last_response.content or "(em xin lỗi, em hơi loạn)"
```

- Max depth = 5 → ngăn loop dại
- Retry: 2 lần trên transient error (timeout, 5xx, rate-limit)
- Mỗi tool call có timeout (default 30s)
- Log mọi tool call vào `tool_call_log` để debug

## 6.4 Context window & memory tier

### 4 tier memory (Letta-inspired, lean MVP)

| Tier | Chứa | Sống ở | Inject vào context khi |
|---|---|---|---|
| **Boss profile** (core, ALWAYS) | tone preference, aliases ("anh Tân" = "Nguyễn Văn Tân"), TZ, frequent contacts | `users.boss_profile` JSONB | Mọi op |
| **Group note** (core per-group) | rolling document, decisions, open tasks | `group_notes.content` (đã có §4) | NoteUpdater, InGroupResponder, DMResponder (khi hỏi group đó) |
| **Session scratchpad** (working, ephemeral) | last N turn của DM hiện tại (text + tool result tóm tắt) | in-memory LRU cache, key=(boss_id, "dm"), TTL 30 min | DMResponder (multi-turn DM coherence) |
| **Archival** (out-of-context, search-only) | full message history | `messages` + Qdrant (đã có §5) | Khi LLM gọi `search_history` tool |

### Boss profile shape (MVP)

```json
{
  "tone":              "lịch sự",                    // 'lịch sự' | 'thẳng thắn' | 'thân mật'
  "preferred_name":    "anh Đạt",                    // bot gọi sếp thế nào
  "aliases": {
    "anh Tân":         "Nguyễn Văn Tân",
    "chị Mai":         "Lê Thị Mai (sale lead)"
  },
  "common_groups":     ["sale_q2", "doi_tac_a"],     // top groups (cache)
  "habits": {
    "morning_review":  "8:30",                       // khi sếp hay hỏi tóm tắt
    "weekly_digest":   "T6"
  }
}
```

Tool `update_boss_profile(key, value)` cho agent tự ghi khi sếp nói
"cứ gọi tôi là Đạt nhé" hay "chị Mai đó là Lê Thị Mai team sale".
Phase 1 add `reflective_pass` job nightly đọc message gần đây + tự
update profile.

### Context budget per op

| Op | Smart model budget | Cấu trúc context |
|---|---|---|
| NoteUpdater | ~8k tokens | system prompt + **boss_profile (~300t)** + note hiện tại (~2k) + template descriptor (~500t) + delta messages (~5k, trim đầu nếu quá) |
| InGroupResponder | ~6k tokens | system prompt + **boss_profile** + group_note (~2k) + retrieval top-20 (~2k) + recent 10 msg (~1k) |
| DMResponder | ~10k tokens | system prompt + **boss_profile** + **session_scratchpad (~1k)** + (group_note nếu hỏi 1 nhóm) (~2k) + retrieval (~3k) + recent DM history (~2k) + tools list (~2k) |

Token counter (tiktoken hoặc provider-native) enforce hard limit. Trim
policy theo thứ tự:
1. Drop messages cũ nhất trong delta
2. Drop retrieval kết quả thấp điểm
3. Truncate group_note giữ section `Cần sếp xử lý`, `Đang tắc`, `Việc đang mở` (drop `Đã quyết` nếu buộc)

## 6.5 Feature × tier routing

Trong cùng 1 op, từng feature có "tier" khác nhau. Router LLM lookup
bảng `feature_routing` ở [§7.3](./07-llm-abstraction.md#73-router--feature-routing).
3 tier: **smart / fast / vision**. Bảng ngắn cho agent layer:

| Feature | Tier | Lý do |
|---|---|---|
| Quick ack ("vâng", "đã ghi") | fast | latency UX |
| Intent classify (DM phân loại) | fast | output JSON ngắn, fast model đủ |
| Q&A với retrieval | smart | reasoning + đa nguồn |
| Note rebuild | smart | structured generation dài |
| Reminder parse (text → due_at, target) | fast | task structured ngắn |
| Action item extract từ message stream | fast | nhiều call, cost-sensitive |
| Summarize group / cross-group | smart | reasoning + structured |
| Fetch URL + summarize | smart | sau khi extract content thì cần hiểu |
| **Image extract** (capture: describe + OCR) | **vision** | cần vision capability, dùng fast vision (gpt-4o-mini, gemini-flash) để rẻ |
| **Image Q&A** (`@bot ảnh này nói gì`) | **vision** | sếp hỏi ảnh trực tiếp |
| Plugin tool (Phase 1+) | tuỳ plugin | declare trong manifest |

## 6.6 Đã chốt & defer

- Single-agent per op, 3 op tách biệt. Multi-agent (LangGraph-style) defer Phase 2.
- Tool call caching defer (`list_groups`, `list_reminders` đổi hiếm — cân nhắc cache 60s khi đo thấy hot).
