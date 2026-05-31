[← Index](./README.md)

# §15. Agent dispatch & extension model

Section này chốt **pattern dùng để khai báo và dispatch** mọi extension
point trong app — operation, tool, memory, retrieval, LLM gateway,
trigger, media adapter, resolver. Mục đích: spec đồng bộ 1 pattern,
thay vì mỗi chỗ 1 kiểu (DB-backed ở §7/§4.9, hardcoded code ở
§6.1/§5.3/§5.4 → mở rộng và đưa lên web sau bị tù).

Reference 2026: **Pydantic AI** capabilities + **OpenAI Agents SDK**
handoffs + **AG2 v0.4** event-driven core + **Anthropic "Building
Effective Agents"** ("simple composable patterns > complex abstractions").

## 15.1 Nguyên tắc cứng

1. **Declarative over imperative** — extension point khai báo qua
   decorator/manifest, không qua `if/elif` trong router code.
2. **Registry + Protocol interface** — mỗi concept có 1 Protocol +
   1 registry. Add implementation = drop file + decorator, **không
   sửa core**.
3. **Config classification** — config có khả năng A/B, per-boss
   override, hot-tune **phải DB-backed ngay MVP** (seed 1 row OK).
   Code chỉ chứa default + interface. Xem §15.11.
4. **DI context (deps_type dataclass)** — handler nhận `Context`
   typed, không tự load entity / không pull global. Test mock context.
5. **Event-driven dispatch** — mọi mutation publish EventBus.
   Subscriber declare qua decorator. Không hardcode call site.

## 15.2 Capability bundle = Operation

Operation = **bundle khai báo** chứa: tools whitelist + prompt key +
model tier + memory tier list + timeout + progress mode + DI context
type. Match Pydantic AI `Capability` + OpenAI Agents SDK `Agent(...)`.

```python
# src/agents/dm_responder.py

@dataclass
class DMContext:                              # deps_type
    boss: Boss
    memory: MemoryProvider
    retriever: Retriever
    llm: LLMGateway
    bus: EventBus
    db: Database

@operation(
    name="dm_responder",
    triggered_by=["message.captured"],         # subscribe via EventBus
    when=lambda e: e.chat_type == "dm" and e.sender_is_boss,
    deps_type=DMContext,
    prompt_key="dm_general",                   # link prompt registry §7.6
    feature="dm_general",                      # link LLM gateway §7.3
    memory_scopes=["semantic", "episodic"],    # §15.5 mem provider scopes
    tools=["search_history", "list_groups",
           "set_reminder", "pin_message",
           "find_exact_quote", "remember", "forget",
           "fetch_url"],
    timeout_s=15,
    progress_mode="quick_ack",                 # §14.3 mitigation
    max_concurrency_per_bot_account=3,
)
class DMResponder(Operation):
    async def handle(self, event: InboundMessage, ctx: DMContext) -> OpResult:
        ...
```

**Lợi:**
- Thêm op mới (`WeeklyDigestor`, `StalledDetector`, `NoteCompactor`,
  ...) = drop file + decorator. Router code không sửa.
- `tools=[...]` chính là **security boundary** — dispatcher reject
  call ngoài whitelist (defense in depth, §12).
- `progress_mode="quick_ack"` declare → engine apply pattern §14.3.2
  generic, không lặp lại logic mỗi op.
- Unit test = mock `DMContext` (DI clean), test op cách ly.

## 15.3 Event dispatcher thay router code

`§6.1` `route()` if/elif **xoá**. Thay bằng:

```python
# src/agents/dispatcher.py — ~30 dòng, không sửa khi add op

class OperationDispatcher:
    def __init__(self, registry: OperationRegistry, bus: EventBus):
        for op_cls in registry.all():
            for event_name in op_cls.triggered_by:
                bus.subscribe(event_name, self._make_handler(op_cls))

    def _make_handler(self, op_cls):
        async def handler(event):
            if op_cls.when and not op_cls.when(event):
                return
            ctx = await build_context(op_cls.deps_type, event)
            async with trace_op(op_cls.name, ctx.boss.id):
                async with concurrency_gate(op_cls, event):
                    await op_cls().handle(event, ctx)
        return handler
```

Channel adapter chuẩn hoá inbound → `EventBus.publish("message.captured", event)`.
Dispatcher tự fan-out cho mọi op subscribe + predicate match. Match
Anthropic **Routing pattern** + Confluent **Orchestrator-Worker pub/sub**.

### Registry mechanism (auto-scan)

KHÔNG dùng filesystem auto-discovery (`importlib.iter_modules`) —
import-time order khó debug. Explicit import:

```python
# src/agents/__init__.py
from .note_updater import NoteUpdater       # noqa: F401 — decorator self-register
from .in_group_responder import InGroupResponder
from .dm_responder import DMResponder
from .reminder_firer import ReminderFirer

# src/agents/registry.py
_REGISTRY: dict[str, type[Operation]] = {}

def operation(name: str, **kwargs):
    def deco(cls):
        cls._op_config = OpConfig(name=name, **kwargs)
        _REGISTRY[name] = cls
        return cls
    return deco

class OperationRegistry:
    @staticmethod
    def all() -> list[type[Operation]]:
        return list(_REGISTRY.values())
```

Pattern áp dụng cho mọi registry: tool, memory provider, retrieval
stage, media adapter, resolver. Decorator chạy at import time → registry
self-populate. Plugin loader (§8.6) thêm 1 lớp scan `plugins/*/tools.py`
qua `importlib.import_module(f"plugins.{name}.tools")` — explicit, có
log "loaded plugin X tools=[...]" để debug.

## 15.4 Tool registry — core + plugin unified

§6.3 14 core tool và §8 plugin tool hiện 2 cơ chế. Unify:

```python
# src/tools/registry.py

@tool(
    name="search_history",
    description="Hybrid retrieval trên messages",
    parameters={...},                          # JSON Schema
    feature="qa_with_search",                  # link LLM gateway tier
    cost_class="medium",
    available_to={"dm_responder",              # whitelist by op
                  "in_group_responder"},
    rate_limit="search:{boss_id}:30/min",
    timeout_s=10,
    parallel_safe=True,                        # §14.3 parallel tool calls
)
async def search_history(query: str, group: str | None,
                          ctx: ToolContext) -> ToolResult:
    ...
```

Plugin tool dùng cùng decorator (import từ `app.plugin_api`).
Dispatcher build per-op tool list = `registry.filter(op_name)`.
`CORE_TOOLS` constant **xoá**.

## 15.5 Memory provider abstraction

§6.4 hiện 4 tier hardcoded → khi muốn swap sang **mem0 / Letta / Zep**
(các framework 2026 chuẩn) phải refactor. Đổi sang Protocol:

```python
# src/memory/base.py

class MemoryScope(StrEnum):
    SEMANTIC   = "semantic"      # facts, preferences (boss_profile)
    EPISODIC   = "episodic"      # past interactions, decisions
    PROCEDURAL = "procedural"    # learned rules, behaviors

class MemoryProvider(Protocol):
    async def recall(self, scope: MemoryScope, query: str,
                     boss_id: int, k: int = 5) -> list[Memory]: ...
    async def write(self, scope: MemoryScope, content: str,
                    boss_id: int, meta: dict) -> None: ...
    async def forget(self, memory_id: str, boss_id: int) -> None: ...
```

3 implementation plug-and-play:

| Provider | Phase | Lý do |
|---|---|---|
| `InternalMemoryProvider` | MVP | Bảng `memory_entries` (boss_id, scope, key, content, meta_json, qdrant_point_id, created_at). Vector lưu ở **Qdrant** (cùng collection messages, payload `kind='memory_*'`) — không pgvector. Semantic = key-value lookup; episodic = trích từ note version + decisions. |
| `Mem0Provider` | Phase 1 | Wrap mem0 SDK. Token-efficient hierarchical extraction (4/2026 release) |
| `LettaProvider` | Phase 1+ | Self-host alternative — OS-like memory management |

**`group_note` không phải memory** — nó là **artifact** (sản phẩm),
sống ở `group_notes` table riêng. Memory = chứa fact/preference/event
trích từ artifact + chat. Tách concept rõ ràng.

`memory_scopes=[...]` ở `@operation` declare scope nào auto-recall vào
context. Builder query provider, inject vào prompt.

Web management Phase 1: `/admin/memory/:boss_id` xem/edit semantic
facts, audit episodic timeline. Schema provider-agnostic → swap
provider, UI giữ.

## 15.6 Retrieval pipeline stages

§5.3 hiện FTS → vector sequential, không có RRF/MMR/reranker. 2026
standard naive RAG đã chết. Đổi sang pipeline:

```python
# src/retrieval/base.py

class RetrievalStage(Protocol):
    async def run(self, query: str, hits: list[Hit],
                  ctx: RetrievalContext) -> list[Hit]: ...

# Pipeline declarative, config DB:
class RetrievalPipeline:
    stages: list[RetrievalStage]
```

Stage registry (decorator-based):

```python
@retrieval_stage(name="bm25", kind="source")
class BM25Retriever: ...

@retrieval_stage(name="dense", kind="source")
class DenseRetriever: ...

@retrieval_stage(name="parallel_fanout", kind="combinator")
class ParallelFanout: ...

@retrieval_stage(name="rrf", kind="fuser")
class RRFFuser: ...

@retrieval_stage(name="mmr", kind="dedupe")
class MMRDeduper: ...

@retrieval_stage(name="cross_encoder", kind="reranker")
class CrossEncoderReranker: ...

@retrieval_stage(name="colbert", kind="reranker")
class ColBERTReranker: ...
```

Pipeline config trong DB:

```sql
retrieval_pipelines (
  feature        TEXT PRIMARY KEY,                -- 'qa_with_search' | 'note_context' | ...
  stages_json    JSONB NOT NULL,                  -- ordered list of {name, args}
  description    TEXT,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Seed MVP cho `qa_with_search`:

```yaml
stages:
  - {name: parallel_fanout, args: {sources: [bm25, dense], k_each: 30}}
  - {name: rrf,             args: {k: 60}}
  - {name: mmr,             args: {lambda_: 0.5, k_out: 20}}
  # Phase 1 thêm: {name: cross_encoder, args: {model: bge-reranker-v2-m3, k_out: 5}}
```

MVP đã có 3 stage (parallel + RRF + MMR), reranker Phase 1 = add 1
stage vào DB, không sửa code.

`/admin/retrieval-pipelines` Phase 1 → admin chỉnh stage runtime.

## 15.7 LLM gateway abstraction

§7 hiện `LLMClient` 3 impl + `pick_model()` internal function. Đủ cho
MVP nhưng khi muốn swap **LiteLLM/Portkey/Inworld** (gateway control
plane chuẩn 2026) phải gỡ. Đổi sang:

```python
# src/llm/gateway.py

@dataclass
class LLMRequest:
    feature: str                               # routing key
    messages: list[ChatMessage]
    tools: list[ToolSpec] | None
    boss_id: int
    required_caps: set[str] = field(default_factory=set)
    routing_hints: dict = field(default_factory=dict)   # cost_class, latency_target, ...
    cache_prefix_hint: str | None = None       # §15.7.2

class LLMGateway(Protocol):
    async def complete(self, req: LLMRequest) -> LLMResponse: ...
    async def embed(self, texts: list[str], model: str) -> list[list[float]]: ...
```

3 implementation:

| Gateway | Phase | Lý do |
|---|---|---|
| `NativeGateway` | MVP | 2 client (OpenAI compat / Gemini) + `pick_model` dispatch |
| `LiteLLMGateway` | Phase 1 | Single endpoint cho mọi provider, YAML config |
| `PortkeyGateway` | Phase 1+ | Managed: A/B sticky, guardrail, budget cap built-in |

### 15.7.1 Routing rule DB-backed

DB-backed routing với **condition + fallback chain + weight**:

```sql
llm_routes (
  id                  BIGSERIAL PRIMARY KEY,
  feature             TEXT NOT NULL,                -- 'qa_with_search' | ...
  condition_cel       TEXT,                          -- CEL expression, NULL = default
  target_tier         TEXT NOT NULL,                 -- 'smart' | 'fast' | 'vision'
  fallback_chain      JSONB NOT NULL DEFAULT '[]'::jsonb,
                                                    -- [{tier: smart, after_failures: 1},
                                                    --  {tier: fast, after_failures: 2}]
  weight              INTEGER NOT NULL DEFAULT 100,  -- A/B split (Phase 1)
  is_active           BOOLEAN NOT NULL DEFAULT TRUE,
  notes               TEXT,
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_llm_routes_feature ON llm_routes(feature) WHERE is_active;
```

Seed MVP: 1 row/feature, `condition_cel=NULL`, `target_tier` lấy từ
§7.3 bảng cũ. Phase 1 add condition (`boss.tier == 'premium' → smart`,
boss khác → fast), A/B weight.

Match Portkey/Inworld pattern (CEL routing + fallback ladder). Web
`/admin/llm-routes` Phase 1.

### 15.7.2 Prompt caching — bật ngay MVP

§7.7 cũ "prompt caching defer Phase 2" → **sai** trong 2026. OpenAI
prompt cache auto-active (prefix ≥1024 token); Gemini cache explicit;
tận dụng = restructure system prompt thành **stable prefix**:

```
[system prompt — KHÔNG đổi giữa các call]
[boss_profile — đổi ít, đổi → cache miss 1 lần]
[group_note — đổi mỗi update, nhưng trong session ngắn vẫn cache]
[recent delta — luôn đổi]
```

`LLMRequest.cache_prefix_hint` báo gateway: cache đến đoạn nào.
OpenAI prefix-stable auto cache. Gemini explicit `cached_content` API
qua gateway. Free 60–80% input cost cho hot ops (DMResponder cùng sếp
trong session).

Defer Phase 2 chỉ là: prompt cache observability dashboard
(hit-rate metric).

### 15.7.3 Token budget — declarative

`§6.4` hardcoded budget number → đổi sang DB:

```sql
feature_budgets (
  feature                  TEXT PRIMARY KEY,
  max_input_tokens         INTEGER NOT NULL,
  max_output_tokens        INTEGER NOT NULL,
  trim_policy_json         JSONB NOT NULL,
  -- vd ["drop_oldest_delta", "drop_low_score_retrieval",
  --     "truncate_group_note_except_critical"]
  compression_strategy     TEXT NOT NULL DEFAULT 'none',
  -- 'none' | 'llmlingua' | 'summarize_oldest'
  cache_prefix_hint        TEXT,                -- guide §15.7.2
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Seed từ §6.4 number hiện tại. Context builder query bảng này, apply
trim/compression theo policy. Phase 1 add LLMLinguaCompressor cho
retrieval result > N tokens.

Web `/admin/feature-budgets` Phase 1.

## 15.8 Trigger declaration

§4.3 NoteUpdater triggers hardcoded (`debounce 10min OR threshold 30
OR on-demand`) → đổi sang decorator + DB mirror:

```python
@trigger(
    op="note_updater",
    event="message.captured",
    debounce=Debounce(key="boss_id,chat_id", window="10m"),
    threshold=Threshold(key="boss_id,chat_id", count=30),
    on_demand_tools=["refresh_group_note"],
)
```

DB mirror cho hot-tune:

```sql
agent_triggers (
  id              BIGSERIAL PRIMARY KEY,
  op_name         TEXT NOT NULL REFERENCES operations(name),  -- soft FK
  event_name      TEXT NOT NULL,
  debounce_json   JSONB,             -- {key, window}
  threshold_json  JSONB,             -- {key, count}
  enabled         BOOLEAN NOT NULL DEFAULT TRUE,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Decorator = code default. Bảng = override khi có row matching `op_name +
event_name`. Add 4th trigger (`weekly_compaction`, `nightly_reflect`,
...) = add row, code không sửa.

### Engine impl

```python
# src/agents/triggers.py — single TriggerEngine instance per process

class TriggerEngine:
    """Subscribe EventBus, track debounce + threshold state per key,
    fire op khi điều kiện đạt."""

    def __init__(self, bus: EventBus):
        self._debounce_state: dict[str, asyncio.TimerHandle] = {}  # key → pending fire
        self._counters: dict[str, int] = {}                         # key → msg count
        self._lock = asyncio.Lock()

    def attach(self, trigger: TriggerSpec):
        async def handler(event):
            key = trigger.key_fn(event)              # 'boss=42,chat=abc'
            async with self._lock:
                # Threshold: tăng counter, fire nếu đạt
                if trigger.threshold:
                    self._counters[key] = self._counters.get(key, 0) + 1
                    if self._counters[key] >= trigger.threshold.count:
                        await self._fire(trigger, event, reason="threshold")
                        self._counters[key] = 0
                        self._cancel_debounce(key)
                        return
                # Debounce: reset timer
                if trigger.debounce:
                    self._cancel_debounce(key)
                    self._debounce_state[key] = asyncio.get_event_loop().call_later(
                        trigger.debounce.window_sec,
                        lambda: asyncio.create_task(self._fire(trigger, event, reason="debounce"))
                    )
        self.bus.subscribe(trigger.event, handler)

    async def _fire(self, trigger, event, reason):
        await self.bus.publish(f"op.{trigger.op}.fire", {"event": event, "reason": reason})
        self._counters.pop(trigger.key_fn(event), None)
```

State sống ở process memory MVP (single process). Split worker
(>50 sếp, [§2.5](./02-architecture-overview.md#25-đã-chốt)) → state migrate
sang Redis với atomic `INCR` + `SETEX` cho debounce timer. Interface
`TriggerEngine` giữ; chỉ swap state backend.

Trigger fire → publish event `op.<name>.fire` → DispatchEngine
(§15.3) match op `triggered_by=["op.<name>.fire"]` → handler chạy.
Tách `triggered_by` của op khỏi raw inbound event = engine kiểm soát
được rate limiting + scheduling, op handler không tự debounce.

Web `/admin/triggers` Phase 1.

## 15.9 Media adapter registry

§5.4 bảng hardcoded `media_kind → adapter` → registry:

```python
@media_adapter(supports={"url", "youtube"}, priority=10)
class WebExtractor:
    async def extract(self, source: MediaSource, ctx) -> MediaExtractResult: ...

@media_adapter(supports={"pdf", "docx", "xlsx"}, priority=10)
class DocumentExtractor: ...

@media_adapter(supports={"image"}, priority=10, requires_caps={"vision"})
class ImageExtractor: ...
```

Pipeline: first matching adapter wins (priority tie-break). Channel
adapter chỉ cần biết `media_kind`, không biết extractor nào.

Add format mới (vd `audio`, `video_long`) = drop file + decorator.

## 15.10 Resolver chain

`§3.4` `resolve_group_owner` 2-step fallback if-else → chain-of-responsibility:

```python
@resolver(name="group_owner", channel="zalo", priority=10)
class ZaloGroupOwnerResolver: ...

@resolver(name="group_owner", channel="*", priority=5, fallback=True)
class HistoryBasedResolver:
    """Fallback: distinct_senders 30d."""
```

Engine try theo channel-match + priority. Channel khác = drop resolver.

Áp dụng tương tự cho:
- `scope_resolver` (§13.3 reminder scope) — LLM classify primary + rule
  table fallback khi confidence < 0.7 (hybrid routing 2026)
- `chat_type_resolver` (group/dm/page classification per channel)

## 15.11 Config classification — code vs DB

Quy tắc cứng cho mọi config:

| Đặc tính config | Lưu ở | Vd |
|---|---|---|
| Có thể A/B test | **DB** | llm_routes, prompts |
| Có thể per-boss override | **DB** | smart/fast/vision model_id, feature_budgets per-boss (Phase 1) |
| Có thể hot-tune không deploy | **DB** | trigger debounce/threshold, retrieval stages |
| Cần seed default cho install mới | **DB** + seed file | models.yaml, prompts/seed.yaml, feature_budgets seed |
| Code-only constant (struct, interface) | Code | Operation class, Tool decorator, Memory scope enum |

→ MVP có thể seed DB chỉ 1 row → không phải build admin UI ngay, nhưng
**đường lên web đã sẵn**. Add UI Phase 1 = build form trên schema có
sẵn, không phải refactor schema.

Bảng MVP cần có ngay (`agent_triggers`, `retrieval_pipelines`,
`llm_routes`, `feature_budgets`) — seed từ default code, web UI Phase 1.

## 15.12 Inconsistency cần fix (snapshot trước sửa)

Spec hiện tại chia 2 nhóm:

**Đã modern (giữ):**
- §8 plugin tool decorator
- §4.9 note template `sections_json`
- §7.6 prompt registry DB
- §7.2 model registry DB
- §7.3 llm_routes DB (condition + fallback ladder + weight)
- §14.1 EventBus interface

**Còn cứng (sửa):**
- §6.1 Operation Router → §15.3 Event dispatcher
- §6.3 CORE_TOOLS list → §15.4 Tool registry
- §6.4 4 memory tier hardcoded → §15.5 MemoryProvider abstraction
- §5.3 FTS→vector sequential → §15.6 Retrieval pipeline
- §7 LLMClient + pick_model → §15.7 LLMGateway abstraction
- §4.3 NoteUpdater triggers hardcoded → §15.8 @trigger
- §5.4 media adapter mapping → §15.9 @media_adapter
- §3.4 resolve_group_owner if-else → §15.10 resolver chain

Mỗi §nêu trên sửa apply pattern §15 tương ứng.

## 15.13 Đã chốt & defer

- **Đã chốt MVP:**
  - Operation = capability bundle (`@operation` decorator + registry)
  - EventBus dispatcher thay if/elif router (§6.1 xoá)
  - Tool registry unify core + plugin (§6.3 + §8 cùng decorator)
  - MemoryProvider Protocol + `InternalMemoryProvider` MVP; 3 scope (semantic/episodic/procedural)
  - Retrieval pipeline 3 stage (parallel_fanout + RRF + MMR); reranker Phase 1
  - LLMGateway Protocol + `NativeGateway` MVP; LiteLLM/Portkey Phase 1+
  - `llm_routes`, `feature_budgets`, `agent_triggers`, `retrieval_pipelines` table seed MVP
  - Prompt caching bật ngay MVP (stable prefix structure)
  - Media adapter + resolver registry decorator-based
- **Defer:**
  - Web UI cho 4 bảng config trên → Phase 1 (schema sẵn)
  - Mem0 / Letta provider → Phase 1 (interface sẵn)
  - LiteLLM / Portkey gateway → Phase 1 (interface sẵn)
  - ColBERT reranker → Phase 1 (stage sẵn slot)
  - LLMLingua compressor → Phase 1 (compression_strategy slot sẵn)
  - A/B routing weight → Phase 1 (cột sẵn, MVP weight=100 mọi row)
