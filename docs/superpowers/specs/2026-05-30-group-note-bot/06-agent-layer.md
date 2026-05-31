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
| `list_groups()` | Liệt kê group sếp đang link |
| `current_time()` | Thời gian hiện tại theo TZ sếp |
| `fetch_url(url)` | Fetch + extract URL/YouTube/file (port legacy, [§5.4](./05-capture-flow-data-model.md#54-media-ingest)) |

**Plugin tools** (load động per-boss, xem [§8](./08-plugin-architecture.md)).

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

## 6.4 Context window management

Mỗi op có "context budget" theo tier model:

| Op | Smart model budget | Cấu trúc context |
|---|---|---|
| NoteUpdater | ~8k tokens | system prompt (~1k) + note hiện tại (~2k) + delta messages (~5k, trim đầu nếu quá) |
| InGroupResponder | ~6k tokens | system prompt (~1k) + group_note (~2k) + retrieval top-20 (~2k) + recent 10 msg (~1k) |
| DMResponder | ~10k tokens | system prompt (~1k) + (group_note nếu hỏi 1 nhóm) (~2k) + retrieval (~3k) + recent DM history (~2k) + tools list (~2k) |

Token counter (tiktoken hoặc provider-native) enforce hard limit. Trim
policy theo thứ tự:
1. Drop messages cũ nhất trong delta
2. Drop retrieval kết quả thấp điểm
3. Truncate group_note giữ section `Cần sếp xử lý`, `Đang tắc`, `Việc đang mở` (drop `Đã quyết` nếu buộc)

## 6.5 Feature × tier routing

Trong cùng 1 op, từng feature có "tier" khác nhau. Router LLM lookup
bảng `feature_routing` ở [§7.3](./07-llm-abstraction.md#73-router--feature-routing).
Bảng ngắn cho agent layer:

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
| Plugin tool (Phase 1+) | tuỳ plugin | declare trong manifest |

## 6.6 Đã chốt & defer

- Single-agent per op, 3 op tách biệt. Multi-agent (LangGraph-style) defer Phase 2.
- Tool call caching defer (`list_groups`, `list_reminders` đổi hiếm — cân nhắc cache 60s khi đo thấy hot).
