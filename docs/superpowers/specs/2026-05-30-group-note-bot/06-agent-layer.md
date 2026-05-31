[← Index](./README.md)

# §6. Agent layer

Pattern dispatch + extension model dùng chung trong toàn app khai báo
ở [§15](./15-agent-dispatch-extension.md). §6 chỉ list các op cụ thể
+ memory + tool + feature tier; không định nghĩa lại pattern.

## 6.1 Operations — list MVP

3 op chính + 1 op nền. Mỗi op = **capability bundle** declare qua
`@operation` (xem [§15.2](./15-agent-dispatch-extension.md#152-capability-bundle--operation)).

| Operation | Trigger event | `when` predicate | Mục tiêu | Output |
|---|---|---|---|---|
| **GroupNoteUpdater** | `message.captured` | debounce/threshold ([§4.3](./04-group-note.md#43-vòng-đời-update), khai báo qua [§15.8 @trigger](./15-agent-dispatch-extension.md#158-trigger-declaration)) | Rebuild markdown của group_note | UPDATE group_notes |
| **InGroupResponder** | `message.captured` | `chat_type==group AND mentions_bot` | Trả lời tại group | Outbound message |
| **DMResponder** | `message.captured` | `chat_type==dm AND sender_is_boss` | Trả lời sếp riêng | Outbound DM |
| **ReminderFirer** | `reminder.due` (scheduler tick) | n/a | Gửi nhắc đúng nhóm gốc / DM ([§13](./13-reminders-tasks.md)) | Outbound message |

Event dispatcher (xem [§15.3](./15-agent-dispatch-extension.md#153-event-dispatcher-thay-router-code))
fan-out event cho mọi op subscribe + predicate match — **không có
`if/elif` router code**. Add op mới (`WeeklyDigestor`, `StalledDetector`,
`NoteCompactor`, ...) = drop file + decorator.

### Capability bundle ví dụ — DMResponder

```python
@operation(
    name="dm_responder",
    triggered_by=["message.captured"],
    when=lambda e: e.chat_type == "dm" and e.sender_is_boss,
    deps_type=DMContext,
    prompt_key="dm_general",
    feature="dm_general",
    memory_scopes=["semantic", "episodic"],
    tools=["search_history", "list_groups", "list_reminders",
           "set_reminder", "cancel_reminder", "pin_message",
           "find_exact_quote", "remember", "forget", "fetch_url"],
    timeout_s=15,
    progress_mode="quick_ack",
    max_concurrency_per_bot_account=3,
)
class DMResponder(Operation):
    async def handle(self, event, ctx: DMContext) -> OpResult: ...
```

### Per-op cấu hình MVP

| Op | Tools whitelist | Feature key (LLM) | Memory scopes | Progress mode |
|---|---|---|---|---|
| GroupNoteUpdater | `edit_group_note` (internal) | `note_update` | semantic, episodic | none (background) |
| InGroupResponder | core + plugin enabled | `qa_with_search` mặc định; intent re-route | semantic, episodic | quick_ack nếu predicted > 5s |
| DMResponder | full core + plugin | `dm_general` | semantic, episodic | quick_ack |
| ReminderFirer | none (direct send) | n/a | n/a | none |

## 6.2 Single agent per op

Lập luận giữ nguyên: **single-agent per op** (1 LLM call có tool +
tool dispatcher loop) — không multi-agent LangGraph-style — vì:

- Op của mình không phức tạp đến mức cần phân vai
- Multi-agent thường wins khi planning đa bước; ở đây không có
- Cost + latency là constraint thực tế

Giữa các op vẫn "đa agent" theo nghĩa **N op tách biệt = N capability
bundle** với prompt/persona/tier/tool khác nhau (declare ở `@operation`,
không hardcode).

Multi-agent (orchestrator-worker pattern §15 reference Anthropic) **giữ
làm option Phase 2** nếu evaluation cho thấy task quá phức tạp — pattern
sẵn (mỗi op có thể spawn sub-op qua `@operation` mới + `triggered_by`
event nội bộ).

## 6.3 Tool registry & core tools

Mọi tool — core + plugin — declare qua **1 decorator chung**
(xem [§15.4](./15-agent-dispatch-extension.md#154-tool-registry--core--plugin-unified)).
Dispatcher build per-op tool list từ registry; whitelist trong
`@operation.tools` chốt quyền truy cập.

**Core tools (MVP):**

| Tool | Mô tả | feature (tier) | parallel_safe |
|---|---|---|---|
| `search_history(query, group?, days?)` | Hybrid retrieval ([§5.3](./05-capture-flow-data-model.md#53-retrieval-pipeline)) | qa_with_search (smart) | ✓ |
| `read_group_note(group_id)` | Note hiện tại | n/a (DB only) | ✓ |
| `refresh_group_note(group_id)` | Trigger NoteUpdater on-demand | note_update (smart) | ✗ |
| `edit_group_note(group_id, section, content)` | Sửa 1 section | n/a | ✗ |
| `list_action_items(group_id?, status?)` | List task | n/a | ✓ |
| `mark_action_item(item_id, status)` | done/cancel | n/a | ✗ |
| `set_reminder(text, due_at, scope, target?)` | Đặt reminder ([§13](./13-reminders-tasks.md)) | reminder_parse (fast) | ✗ |
| `list_reminders(status?, group?)` | List reminder | n/a | ✓ |
| `cancel_reminder(reminder_id)` | Huỷ | n/a | ✗ |
| `pin_message(message_id, note?)` | Pin → section "Đã pin" | n/a | ✗ |
| `unpin_message(pin_id)` | Bỏ pin | n/a | ✗ |
| `find_exact_quote(fragment, group?)` | FTS exact + context ±3 | n/a | ✓ |
| `remember(key, value)` | Ghi memory semantic về sếp/người xung quanh. Vd `remember("preferred_name", "Đạt")`, `remember("alias:anh Tân", "Nguyễn Văn Tân — sale lead")` ([§6.4](#64-memory-provider)) | n/a | ✗ |
| `forget(memory_id)` | Xoá entry memory (sếp request "đừng nhớ X nữa") | n/a | ✗ |
| `list_groups()` | Group sếp đang link | n/a | ✓ |
| `current_time()` | TZ sếp | n/a | ✓ |
| `fetch_url(url)` | Fetch + extract (port legacy, [§5.4](./05-capture-flow-data-model.md#54-media-ingest)) | url_summarize (smart) | ✓ |

**Plugin tools** load động per-boss qua bảng `boss_integrations`
([§8](./08-plugin-architecture.md)). Cùng `@tool` decorator → registry
merge core + plugin.

### `pins` schema

```sql
pins (
  id              BIGSERIAL PRIMARY KEY,
  boss_id         INTEGER NOT NULL REFERENCES users(id),
  group_note_id   BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
  message_id      BIGINT NOT NULL REFERENCES messages(id),
  note            TEXT,
  pinned_by       INTEGER NOT NULL REFERENCES users(id),
  pinned_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (group_note_id, message_id)
);
CREATE INDEX idx_pins_group ON pins(group_note_id);
```

NoteUpdater render section `Đã pin` (template `behavior='manual_pin'`):
list bullets từ `pins` JOIN `messages`. LLM không sửa.

### `find_exact_quote` impl

```python
@tool(
    name="find_exact_quote",
    parameters={"fragment": {"type": "string"}, "group_id": {"type": "string", "nullable": True}},
    available_to={"dm_responder", "in_group_responder"},
    parallel_safe=True,
)
async def find_exact_quote(fragment: str, group_id: str | None,
                            ctx: ToolContext):
    matches = await ctx.repos.messages.fts_search(
        fragment, ctx.boss.id, group_id, exact=True, limit=5)
    return [{"author": m.sender_name, "ts": m.ts, "full_text": m.text,
             "context_before": before, "context_after": after}
            for m in matches]
```

### Agent loop

```python
async def agent_loop(op_ctx, op_cls, max_depth=5):
    messages = build_initial(op_ctx, op_cls)
    tools = registry.filter(op_cls.name)
    for step in range(max_depth):
        resp = await ctx.llm.complete(LLMRequest(
            feature=op_cls.feature,
            messages=messages,
            tools=tools,
            boss_id=op_ctx.boss.id,
            cache_prefix_hint=op_cls.cache_prefix_hint,
        ))
        if not resp.tool_calls:
            return resp.content
        # Parallel-safe tool calls: gather; otherwise sequential
        await dispatch_tool_calls(resp.tool_calls, op_ctx, messages)
    log.warn("max depth reached")
    return last_response.content or "(em xin lỗi, em hơi loạn)"
```

- Max depth 5 → ngăn loop dại
- Retry 2 lần trên transient error
- Mỗi tool có `timeout_s` declare ở decorator
- Parallel-safe tool calls trong cùng turn → `asyncio.gather` ([§14.3](./14-performance-observability.md#143-latency-targets) mitigation #3)
- Log mọi tool call vào `tool_call_log` (trace_id propagate, [§14.2](./14-performance-observability.md#142-otel-compatible-trace-schema))

## 6.4 Memory provider

§6.4 cũ "4 tier hardcoded" → đổi sang **MemoryProvider Protocol**
(xem [§15.5](./15-agent-dispatch-extension.md#155-memory-provider-abstraction)).
Mục tiêu: swap sang mem0 / Letta Phase 1 không refactor agent.

### 3 scope chuẩn

| Scope | Chứa | Inject vào op khi |
|---|---|---|
| **semantic** | Facts, preferences (tên gọi, alias, tone, habits) | Mọi op |
| **episodic** | Past interactions, decisions, key events | Op có history-sensitive (DMResponder, InGroupResponder) |
| **procedural** | Learned rules (Phase 1: reflective pass nightly tạo) | Phase 1 |

`group_note` **không phải memory** — là **artifact** (sản phẩm
work-product) sống ở `group_notes` table. Note inject vào op context
trực tiếp khi op declare `group_context=True`, không qua MemoryProvider.

### Storage MVP — `InternalMemoryProvider`

```sql
memory_entries (
  id              BIGSERIAL PRIMARY KEY,
  boss_id         INTEGER NOT NULL REFERENCES users(id),
  scope           TEXT NOT NULL,            -- 'semantic' | 'episodic' | 'procedural'
  key             TEXT,                     -- nullable cho episodic; SET cho semantic (vd 'preferred_name', 'alias:anh Tân')
  content         TEXT NOT NULL,
  meta_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
  qdrant_point_id TEXT,                     -- NULL nếu không cần semantic search; SET khi upsert Qdrant
  source          TEXT NOT NULL,            -- 'agent_tool' | 'reflective' | 'manual'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (boss_id, scope, key)              -- semantic upsert by key; episodic key=NULL → multi-row
);
CREATE INDEX idx_memory_boss_scope ON memory_entries(boss_id, scope);

-- Vector cho semantic recall: KHÔNG dùng pgvector. Cùng Qdrant
-- collection với messages, payload {boss_id, kind: 'memory_semantic' |
-- 'memory_episodic', memory_id}. `qdrant_point_id` lưu point UUID để
-- delete khi forget.
```

**Semantic shape** (key-value/text) — boss_profile cũ chuyển sang đây:

| key | value |
|---|---|
| `tone` | "lịch sự" |
| `preferred_name` | "anh Đạt" |
| `alias:anh Tân` | "Nguyễn Văn Tân" |
| `alias:chị Mai` | "Lê Thị Mai (sale lead)" |
| `habit:morning_review` | "8:30" |

Tool `remember(key, value)` thực chất là
`memory.write(scope=SEMANTIC, key=key, content=value)`. Agent tự ghi
khi sếp nói "cứ gọi tôi là Đạt".

**Episodic**: append-only khi `note.updated` event (subscriber trích key
decision + outcome). Phase 1 add reflective pass nightly.

### Context budget per op

Số token budget hardcoded cũ → **declarative** qua `feature_budgets`
table ([§15.7.3](./15-agent-dispatch-extension.md#1573-token-budget--declarative)).
Seed MVP:

| Op | feature | max_input_tokens | trim_policy |
|---|---|---|---|
| NoteUpdater | note_update | 8000 | drop_oldest_delta |
| InGroupResponder | qa_with_search | 6000 | drop_low_score_retrieval, drop_oldest_recent |
| DMResponder | dm_general | 10000 | drop_low_score_retrieval, drop_oldest_episodic |

Prompt cache prefix hint declarable per-op ([§15.7.2](./15-agent-dispatch-extension.md#1572-prompt-caching--bật-ngay-mvp)):
stable prefix = system prompt + semantic memory + group_note (nếu có).
Free 60–80% input cost cho DMResponder hot sessions.

## 6.5 Feature × tier routing

Routing rule lưu ở DB (`llm_routes` table, [§15.7.1](./15-agent-dispatch-extension.md#1571-routing-rule-db-backed)).
Mapping seed MVP:

| Feature | Default tier | Lý do |
|---|---|---|
| Quick ack ("vâng", "đã ghi") | fast | latency UX |
| Intent classify | fast | output JSON ngắn |
| `qa_with_search` | smart | reasoning đa nguồn |
| `note_update` | smart | structured generation dài |
| `reminder_parse` | fast | task structured ngắn |
| `action_item_extract` | fast | nhiều call, cost-sensitive |
| `summarize_group` / `summarize_cross_group` | smart | reasoning |
| `url_summarize` | smart | reasoning sau extract |
| `image_extract` (capture) | vision | describe + OCR, fast vision |
| `image_qa` (sếp `@bot ảnh này nói gì`) | vision | reasoning trên ảnh |
| `dm_general` | smart | trợ lý cá nhân |

Phase 1: add condition_cel cho A/B (`boss.tier == 'premium' → smart`,
else fast), fallback chain (`smart → fast khi 5xx`).

## 6.6 Đã chốt & defer

- Single-agent per op, N op tách biệt qua capability bundle. Multi-agent (orchestrator-worker) defer Phase 2 (pattern sẵn).
- Tool registry unify core + plugin ([§15.4](./15-agent-dispatch-extension.md#154-tool-registry--core--plugin-unified)).
- MemoryProvider Protocol + InternalMemoryProvider MVP. Mem0/Letta Phase 1 ([§15.5](./15-agent-dispatch-extension.md#155-memory-provider-abstraction)).
- Token budget + trim policy DB-backed ([§15.7.3](./15-agent-dispatch-extension.md#1573-token-budget--declarative)).
- Prompt caching bật ngay MVP qua stable prefix structure ([§15.7.2](./15-agent-dispatch-extension.md#1572-prompt-caching--bật-ngay-mvp)).
- Tool call caching defer (cân nhắc khi đo hot calls).
