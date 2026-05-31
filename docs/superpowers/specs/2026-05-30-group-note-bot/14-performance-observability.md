[← Index](./README.md)

# §14. Performance, latency & observability

3 thứ gắn chặt nhau, gom 1 section:

1. **EventBus internal** — decouple capture pipeline + foundation cho webhook dispatcher Phase 1
2. **OTel-compatible trace schema** — log LLM call theo OpenTelemetry GenAI convention; swap-in Langfuse/Phoenix Phase 1 free
3. **Latency targets + mitigation** — bot "feel nhanh" như thư ký, không feel như form gửi đi đợi reply

## 14.1 EventBus internal

### Lý do

Hiện tại capture pipeline hardcode sequential: webhook → router → DB
insert → schedule NoteUpdater. Thêm 1 step (PII redact, custom hook,
webhook outbound Phase 1) = refactor code core.

Pattern n8n/OpenClaw: mọi mutation publish event lên bus, subscriber tự
đăng ký. Add step = add subscriber, không sửa publisher.

### Schema interface

```python
# src/events/bus.py
from typing import Protocol, Awaitable, Callable

EventName = str   # 'message.captured' | 'note.updated' | 'reminder.fired' | 'llm.call.completed' | ...
EventPayload = dict

class EventBus(Protocol):
    async def publish(self, event: EventName, payload: EventPayload) -> None: ...
    def subscribe(self, event: EventName, handler: Callable[[EventPayload], Awaitable[None]]) -> None: ...

class InMemoryEventBus:
    """asyncio-based, in-process. Subscribers chạy concurrently, mỗi handler
    có timeout 10s mặc định, error không block publisher."""
```

### Sự kiện chuẩn (MVP)

| Event | Publisher | Payload (chính) | Subscriber MVP |
|---|---|---|---|
| `message.captured` | Channel router | `{message_id, boss_id, provider, chat_id, ts}` | NoteUpdater scheduler, metrics |
| `message.media_extracted` | Media pipeline | `{message_id, media_kind, chars}` | metrics |
| `note.updated` | NoteUpdater | `{group_note_id, boss_id, version, sections_changed}` | metrics, action_items extractor, SSE pusher (§9.5 live preview) |
| `action_item.created` | LLM extract | `{item_id, boss_id, group_note_id}` | metrics |
| `action_item.status_changed` | DM tool / web | `{item_id, from, to}` | metrics |
| `reminder.set` | set_reminder tool | `{reminder_id, boss_id, due_at}` | metrics |
| `reminder.fired` | ReminderFirer | `{reminder_id, boss_id, status}` | metrics |
| `bot_account.status_changed` | health check | `{bot_account_id, from, to, reason}` | admin notifier |
| `llm.call.started` | LLM client wrapper | `{trace_id, span_id, feature, model, ...}` | trace store |
| `llm.call.completed` | LLM client wrapper | `{trace_id, span_id, tokens_in, tokens_out, latency_ms, status}` | trace store, token_usage, metrics |
| `tool.call.started/completed` | Tool dispatcher | `{trace_id, span_id, tool_name, args_hash, latency_ms, status}` | trace store |

Phase 1 add subscriber:
- **Webhook dispatcher** — POST tới `outbound_webhooks` table theo filter
- **Public API SSE** — push event tới `/api/public/v1/events` cho boss subscribe
- **Langfuse exporter** — forward `llm.call.completed` tới Langfuse OTLP endpoint

### Trade-off

In-memory MVP: dễ debug, chỉ chạy 1 process. Khi split web/worker
(>50 sếp, [§2.5](./02-architecture-overview.md#25-đã-chốt)) → swap impl
sang Redis Streams / NATS, interface giữ nguyên.

## 14.2 OTel-compatible trace schema

### Lý do

Log token_usage tự khai sẽ tạo cost refactor khi muốn tích Langfuse /
Phoenix Arize. Đặt tên field theo **OpenTelemetry GenAI semantic
convention** ngay từ MVP → exporter Phase 1 chỉ là wrapper.

### Schema

```sql
-- Update token_usage table (đã có §7.5) với OTel-aligned fields:
ALTER TABLE token_usage
  ADD COLUMN trace_id           TEXT,
  ADD COLUMN span_id             TEXT,
  ADD COLUMN parent_span_id      TEXT,
  ADD COLUMN gen_ai_system       TEXT,          -- 'openai' | 'anthropic' | 'gemini' (OTel attr)
  ADD COLUMN gen_ai_request_model TEXT,
  ADD COLUMN gen_ai_response_model TEXT,
  ADD COLUMN gen_ai_operation_name TEXT;        -- 'chat' | 'embed'

-- Tool call log (mới):
CREATE TABLE tool_call_log (
  id              BIGSERIAL PRIMARY KEY,
  trace_id        TEXT NOT NULL,
  span_id         TEXT NOT NULL,
  parent_span_id  TEXT,
  boss_id         INTEGER NOT NULL REFERENCES users(id),
  tool_name       TEXT NOT NULL,
  args_hash       TEXT NOT NULL,                 -- sha256(args_json) để cache lookup
  status          TEXT NOT NULL,                 -- 'ok' | 'error' | 'timeout'
  latency_ms      INTEGER NOT NULL,
  error           TEXT,
  called_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_tool_call_log_trace ON tool_call_log(trace_id);
```

### Trace ID propagation

Mỗi op (NoteUpdater / Responder) generate `trace_id` = uuid4 hex. Span
cho từng LLM call + tool call + retrieval, parent_span_id link.

Code helper:

```python
@contextmanager
def trace_op(op_name: str, boss_id: int):
    ctx = TraceContext(trace_id=uuid4().hex, root_span_id=uuid4().hex, op=op_name, boss_id=boss_id)
    token = current_trace.set(ctx)
    try:
        yield ctx
    finally:
        current_trace.reset(token)

# In handler:
async def handle_dm(event):
    with trace_op("dm_responder", event.boss_id) as ctx:
        await agent_loop(...)   # llm + tool calls đều pick ctx từ contextvar
```

### Langfuse swap (Phase 1)

Khi enable: add subscriber tới `llm.call.completed` + `tool.call.completed`
events → format payload theo Langfuse Python SDK → POST. KHÔNG refactor
DB schema, KHÔNG refactor code call.

## 14.3 Latency targets

### Budget per op (end-to-end, mục tiêu p50)

| Op | Budget | Phân rã |
|---|---|---|
| Quick ack ("@bot vâng") | **2–4s** | poll(1–3s) + LLM-fast(400–800ms) + send(200ms) |
| In-group Q&A có search | **6–12s** | poll + retrieval(300ms) + LLM-smart(2–4s) + tool + LLM(2–4s) |
| DM Q&A cross-group | **8–15s** | retrieval + LLM-smart agent loop 2–3 iter |
| Set reminder via chat | **3–5s** | poll + LLM-fast parse(500ms) + DB insert |
| Reminder fire (scheduler) | **<500ms** | no LLM, direct send |
| Note rebuild (async, không user wait) | 5–15s background | LLM-smart structured |
| Image extract capture (async) | 1–2s background | vision-fast |
| Web load `/groups/:id` | <1s | server-render + 1 DB query |

p99 budget = p50 × 2.5 cho ops có LLM (LLM tail latency cao).

### Mitigation playbook

1. **Typing indicator** — Zalo personal có API "đang gõ" (legacy có).
   Show ngay khi nhận `@bot`. Giảm perceived wait từ "đợi" → "đang nghĩ".

2. **Quick ack pattern cho op dài** — op `qa_with_search` predicted > 5s:
   - LLM-fast classify intent (<500ms) → reply ngay "Để em check..."
   - Continue agent loop → send full answer (qua message thứ 2)
   - Pattern dùng cho: `qa_with_search`, `summarize_group`, `summarize_cross_group`

3. **Parallel tool calls** — LLM trả về N tool call cùng turn → `asyncio.gather`
   chạy đồng thời (không sequential). Giảm 30–50% latency agent loop.
   Cần: tools không có dep chéo, dispatcher support batch.

4. **Fast-tier default** — `feature_routing` default `fast`; chỉ feature
   đánh dấu rõ `smart` mới dùng smart. Hiện đã apply ở [§7.3](./07-llm-abstraction.md#73-router--feature-routing).

5. **Pre-warm context cache** — group có activity 7d gần đây:
   - Giữ `group_notes.content` + `boss_profile` trong in-memory LRU cache (200 entries, TTL 30 min)
   - Miss = fresh DB load (~20ms extra)

6. **Aggressive timeout + degrade**:
   - LLM-smart timeout 8s → fallback LLM-fast với note "Em trả lời nhanh, có thể chưa kỹ"
   - LLM-fast timeout 4s → reply "Em đang chậm, anh nhắc lại sau ít phút"
   - Tool timeout 30s → drop tool result, LLM thử tool khác hoặc trả lời thiếu

7. **Streaming Phase 1** — Zalo personal nếu support edit-message → stream
   chunks bằng edit. Phase 0 không làm (chưa verify capability ở spike).

### Đo + alert

Metrics Prometheus (đã có §10.5):
- `llm_call_latency_seconds{feature, tier, status}` histogram
- `op_latency_seconds{op}` histogram
- `agent_loop_iterations{op}` histogram

Alert (Phase 1):
- p95 latency `in_group_responder` > 15s 5 phút liên tục
- LLM error rate > 5% 5 phút liên tục
- Bot acc rate_limited > 3 acc trong 1h

## 14.4 Đã chốt & defer

- EventBus in-memory MVP, swap Redis Streams/NATS khi split worker.
- OTel-aligned schema ngay từ MVP, Langfuse exporter Phase 1.
- Latency target = "feel thư ký" (2–12s tuỳ op), không phải "feel ChatGPT" (<1s không khả thi với Zalo personal).
- Streaming response → Phase 1 sau spike verify Zalo capability.
- Distributed tracing OpenTelemetry collector → Phase 2.
