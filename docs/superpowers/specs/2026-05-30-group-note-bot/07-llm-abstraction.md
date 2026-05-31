[← Index](./README.md)

# §7. LLM abstraction

Pattern gateway + routing rule khai báo ở
[§15.7](./15-agent-dispatch-extension.md#157-llm-gateway-abstraction).
§7 chốt interface + impl MVP + bảng cấu hình.

## 7.1 LLMGateway

```python
@dataclass
class LLMRequest:
    feature: str                                  # routing key
    messages: list[ChatMessage]
    tools: list[ToolSpec] | None
    boss_id: int
    required_caps: set[str] = field(default_factory=set)   # vd {"vision", "json_mode"}
    routing_hints: dict = field(default_factory=dict)       # cost_class, latency_target_ms, ...
    cache_prefix_hint: str | None = None          # §7.5 prompt caching
    max_output_tokens: int | None = None
    temperature: float = 0.7

class LLMGateway(Protocol):
    async def complete(self, req: LLMRequest) -> LLMResponse: ...
    async def embed(self, texts: list[str], model: str) -> list[list[float]]: ...
```

3 implementation roadmap:

| Gateway | Phase | Đặc tính |
|---|---|---|
| `NativeGateway` | **MVP** | 2 provider client trong process (OpenAI compat — cover OpenAI + Groq + others; Gemini); routing qua `llm_routes` (§7.3); failover ladder; prompt cache headers per provider |
| `LiteLLMGateway` | Phase 1 | Wrap LiteLLM endpoint (single endpoint cho mọi provider, YAML config) |
| `PortkeyGateway` | Phase 1+ | Managed gateway: A/B sticky, guardrail, budget cap, observability built-in |

NativeGateway compose 2 client thấp tầng (MVP):

- `OpenAICompatibleClient(base_url, api_key)` — cover OpenAI, Groq,
  OpenRouter, DeepSeek, Cerebras, Fireworks, Together, xAI, Ollama, vLLM
- `GeminiClient(api_key)` — schema khác

Anthropic client **không build** cho project này (user chốt).
Architecture vẫn cho phép add sau qua Protocol nếu đổi ý.

Client level chỉ làm wire-protocol mapping; routing/fallback/caching ở
gateway level.

## 7.2 ModelRegistry — DB + seed file

Nguồn dữ liệu vừa file vừa DB:
- `config/models.yaml` = seed mặc định khi setup mới
- Bảng `models` trong DB = source of truth runtime
- Startup: bảng rỗng → load seed. Sau đó DB override

```sql
models (
  id                       BIGSERIAL PRIMARY KEY,
  name                     TEXT NOT NULL,
  provider                 TEXT NOT NULL,                  -- 'openai' | 'groq' | 'gemini' | 'custom'
  endpoint_kind            TEXT NOT NULL,                  -- 'openai_compat' | 'gemini'
  base_url                 TEXT,
  tier                     TEXT NOT NULL,                  -- 'smart' | 'fast' | 'vision'
  ctx_max                  INTEGER NOT NULL,
  capabilities             JSONB NOT NULL DEFAULT '[]',    -- ['tool_use', 'vision', 'json_mode', 'prompt_cache']
  cost_per_1m_input_usd    NUMERIC(10, 4),
  cost_per_1m_output_usd   NUMERIC(10, 4),
  is_platform_default      BOOLEAN NOT NULL DEFAULT FALSE,
  is_active                BOOLEAN NOT NULL DEFAULT TRUE,
  notes                    TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (provider, name)
);
```

### MVP platform defaults

Anh chốt mapping:

| Slot | Provider | Model | Capability |
|---|---|---|---|
| **smart** | OpenAI | `gpt-4o-mini` | tool_use, vision, json_mode, prompt_cache |
| **fast** | Groq | `llama-3.3-70b-versatile` | tool_use |
| **vision** | OpenAI | `gpt-4o-mini` (qua fallback: smart slot có vision) | tool_use, vision |

Vision slot **không cần seed riêng** vì:
- Smart default = gpt-4o-mini đã có `vision` capability
- §7.4 fallback logic: `tier=vision` mà slot trống + smart có vision → dùng smart slot

Khi sếp đổi smart sang model không vision (vd gpt-4o, llama), web
`/settings/ai` cảnh báo "Smart anh chọn không có vision — set vision
slot riêng nếu cần đọc ảnh." Dropdown gợi ý `gpt-4o-mini`.

Seed `config/models.yaml`:

```yaml
- name: gpt-4o-mini
  provider: openai
  endpoint_kind: openai_compat
  base_url: https://api.openai.com/v1
  tier: smart
  ctx_max: 128000
  capabilities: [tool_use, json_mode, vision, prompt_cache]
  cost_per_1m_input_usd: 0.15
  cost_per_1m_output_usd: 0.60
  is_platform_default: true
  notes: MVP default cho smart + vision (fallback)

- name: llama-3.3-70b-versatile
  provider: groq
  endpoint_kind: openai_compat
  base_url: https://api.groq.com/openai/v1
  tier: fast
  ctx_max: 128000
  capabilities: [tool_use]
  cost_per_1m_input_usd: 0.59
  cost_per_1m_output_usd: 0.79
  is_platform_default: true
  notes: MVP default cho fast

# Các model dưới đây active=true để sếp tự chọn, không phải platform default:

- name: gpt-4o
  provider: openai
  endpoint_kind: openai_compat
  base_url: https://api.openai.com/v1
  tier: smart
  ctx_max: 128000
  capabilities: [tool_use, json_mode, vision, prompt_cache]
  cost_per_1m_input_usd: 2.50
  cost_per_1m_output_usd: 10.00
  is_platform_default: false
  notes: Upgrade smart khi sếp cần reasoning sâu

- name: gemini-2.0-flash
  provider: gemini
  endpoint_kind: gemini
  tier: fast
  ctx_max: 1000000
  capabilities: [tool_use, vision]
  cost_per_1m_input_usd: 0.10
  cost_per_1m_output_usd: 0.40
  is_platform_default: false
  notes: Alt fast với vision built-in
```

Superadmin CRUD `/admin/models` ([§9.3](./09-web-admin.md#93-sitemap-superadmin-pages)).
Sếp chọn model qua `/settings/ai` chỉ từ pool `is_active=true`. Sếp
chưa config → fallback `is_platform_default` cùng tier.

Platform key cho free trial / fallback (sếp chưa BYO key):
- `PLATFORM_OPENAI_API_KEY` env (smart + vision)
- `PLATFORM_GROQ_API_KEY` env (fast)

(Xem [§10.4](./10-tech-stack-infra.md#104-env-config))

## 7.3 Routing — `llm_routes` table

Routing rule DB-backed với **condition + fallback chain + weight**
(match Portkey/Inworld 2026):

```sql
llm_routes (
  id                  BIGSERIAL PRIMARY KEY,
  feature             TEXT NOT NULL,                  -- 'qa_with_search' | 'note_update' | ...
  condition_cel       TEXT,                            -- NULL = default rule
  target_tier         TEXT NOT NULL,                   -- 'smart' | 'fast' | 'vision'
  fallback_chain      JSONB NOT NULL DEFAULT '[]'::jsonb,
                                                      -- [{tier: 'fast', after_failures: 1},
                                                      --  {tier: 'smart', after_failures: 2,
                                                      --   provider_blacklist: ['openai']}]
  weight              INTEGER NOT NULL DEFAULT 100,    -- A/B split Phase 1; MVP weight=100 every row
  is_active           BOOLEAN NOT NULL DEFAULT TRUE,
  notes               TEXT,
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_llm_routes_feature ON llm_routes(feature) WHERE is_active;
```

Sếp config slot ở `/settings/ai` (3 cột `users.smart_model_id`,
`fast_model_id`, `vision_model_id` + `api_keys_enc`). Routing logic:

```python
async def pick_model(req: LLMRequest, boss: Boss) -> Model:
    # 1. Match llm_routes by feature + condition_cel (truthy)
    route = await llm_routes_repo.match(req.feature, boss)
    # 2. Slot model của sếp
    chosen_id = {"smart": boss.smart_model_id,
                 "fast":  boss.fast_model_id,
                 "vision": boss.vision_model_id}[route.target_tier]
    if chosen_id is None:
        # Vision fallback đặc biệt: nếu smart có vision capability
        if route.target_tier == "vision" and has_cap(boss.smart_model_id, "vision"):
            chosen_id = boss.smart_model_id
        else:
            chosen_id = (await platform_default_repo.get(tier=route.target_tier)).id
    return await resolve_capability(chosen_id, req.required_caps, boss)
```

Fallback ladder áp dụng khi LLM call fail (timeout/5xx/rate-limit):
gateway thử `fallback_chain` theo thứ tự.

Seed feature MVP:

| feature | target_tier | fallback_chain |
|---|---|---|
| `note_update` | smart | `[{tier: smart, provider_blacklist: [<primary>]}]` |
| `quick_ack` | fast | `[]` (lỗi → skip) |
| `intent_classify` | fast | `[]` |
| `qa_with_search` | smart | `[{tier: fast, after_failures: 2}]` |
| `summarize_group` | smart | `[]` |
| `summarize_cross_group` | smart | `[]` |
| `action_item_extract` | fast | `[]` |
| `reminder_parse` | fast | `[]` |
| `url_summarize` | smart | `[{tier: fast, after_failures: 1}]` |
| `image_extract` | vision | `[]` |
| `image_qa` | vision | `[{tier: smart, after_failures: 1, required_caps: [vision]}]` |
| `dm_general` | smart | `[{tier: fast, after_failures: 2}]` |

A/B test Phase 1: thêm row cùng feature, khác `condition_cel` (`hash(boss_id) % 100 < 30`),
khác `target_tier`. Weight phân phối traffic.

Cột thêm vào `users`:

```sql
ALTER TABLE users ADD COLUMN smart_model_id  BIGINT REFERENCES models(id);
ALTER TABLE users ADD COLUMN fast_model_id   BIGINT REFERENCES models(id);
ALTER TABLE users ADD COLUMN vision_model_id BIGINT REFERENCES models(id);
ALTER TABLE users ADD COLUMN api_keys_enc    BYTEA;
```

## 7.4 Capability fallback

Feature yêu cầu capability (`vision`, `json_mode`, `tool_use`,
`prompt_cache`) mà model tier chọn không có:

```python
async def resolve_capability(model_id: int, required: set[str], boss: Boss) -> Model:
    m = await models_repo.get(model_id)
    missing = required - set(m.capabilities)
    if not missing:
        return m
    # Try other slot
    for candidate_id in [boss.vision_model_id, boss.smart_model_id, boss.fast_model_id]:
        if candidate_id and not (required - set((await models_repo.get(candidate_id)).capabilities)):
            log.warn(f"capability fallback {m.name} → {candidate_id} ({missing})")
            return await models_repo.get(candidate_id)
    raise CapabilityMissing(required, m.name)
```

Cảnh báo trên web khi save `/settings/ai`: vd "Smart model anh chọn
không có vision; ảnh sẽ dùng Vision slot. Nếu Vision slot trống, dùng
default platform."

## 7.5 Prompt caching — bật ngay MVP

Khác spec cũ "defer Phase 2" — trong 2026 OpenAI prompt cache
auto-active (prefix ≥1024 token) và Gemini explicit cache; free 60–80%
input cost nếu structure đúng.

### Stable prefix pattern

Tổ chức message theo thứ tự **biến đổi tăng dần** (prefix stable →
provider auto-cache):

```
[1. System prompt template — KHÔNG đổi giữa các call]   ← cache here
[2. Semantic memory snapshot — đổi ít (∼daily)]          ← cache here
[3. Group note hiện tại — đổi mỗi update]                ← cache here
[4. Retrieval results — đổi mỗi call]
[5. Recent delta + user message — luôn đổi]
```

`LLMRequest.cache_prefix_hint` báo gateway điểm cắt cache:

```python
LLMRequest(
    feature="dm_general",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": semantic_memory_block},
        {"role": "user",   "content": group_note_block},
        {"role": "user",   "content": retrieval_block},
        {"role": "user",   "content": user_question},
    ],
    cache_prefix_hint="after_group_note",   # cache 3 message đầu
    ...
)
```

OpenAI tự cache nếu prefix > 1024 token (hit-ratio ổn cho session DM).
Gemini cache explicit qua `cached_content` API — gateway xử lý create +
reuse cache id per (boss, feature). Reset cache khi note version update.

### Observability

Metric `llm_cache_hit_ratio{feature, model}` ([§14.2](./14-performance-observability.md#142-otel-compatible-trace-schema))
đo hit-rate. Phase 1 dashboard: hit-rate dưới 50% trên feature
high-volume → alert restructure prompt.

Defer Phase 2 chỉ là **prompt-cache learning** (tự re-order context cho
hit-rate tối ưu).

## 7.6 Token budget — `feature_budgets`

§6.4 budget number hardcoded → đổi sang DB:

```sql
feature_budgets (
  feature                  TEXT PRIMARY KEY,
  max_input_tokens         INTEGER NOT NULL,
  max_output_tokens        INTEGER NOT NULL,
  trim_policy_json         JSONB NOT NULL,
  -- ordered list: ["drop_oldest_delta", "drop_low_score_retrieval",
  --                "truncate_group_note_except_critical",
  --                "drop_oldest_episodic"]
  compression_strategy     TEXT NOT NULL DEFAULT 'none',
  -- 'none' | 'llmlingua' | 'summarize_oldest'
  cache_prefix_hint        TEXT,
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Seed MVP:

| feature | max_input | max_output | trim_policy | compression |
|---|---|---|---|---|
| note_update | 8000 | 4000 | drop_oldest_delta | none |
| qa_with_search | 6000 | 1500 | drop_low_score_retrieval, drop_oldest_recent | none |
| dm_general | 10000 | 2000 | drop_low_score_retrieval, drop_oldest_episodic | none |
| summarize_group | 12000 | 2000 | truncate_group_note_except_critical | none |
| reminder_parse | 1500 | 500 | drop_oldest_delta | none |
| image_extract | 2000 | 800 | n/a | none |

Phase 1: `compression_strategy='llmlingua'` cho `summarize_*` features
khi retrieval > 8k token.

Web `/admin/feature-budgets` Phase 1.

## 7.7 Cost tracking

Mỗi LLM call:

```sql
token_usage (
  id                      BIGSERIAL PRIMARY KEY,
  boss_id                 INTEGER NOT NULL REFERENCES users(id),
  feature                 TEXT NOT NULL,                        -- 'note_update' | 'qa_with_search' | ...
  operation               TEXT NOT NULL,                        -- 'note_updater' | 'in_group' | 'dm' | 'embed'
  provider                TEXT NOT NULL,
  model                   TEXT NOT NULL,
  tokens_in               INTEGER NOT NULL,
  tokens_out              INTEGER NOT NULL,
  tokens_cached           INTEGER NOT NULL DEFAULT 0,           -- prompt cache hit count §7.5
  cost_usd                NUMERIC(10, 6) NOT NULL,
  cost_saved_cache_usd    NUMERIC(10, 6) NOT NULL DEFAULT 0,
  latency_ms              INTEGER NOT NULL,
  trace_id                TEXT,                                  -- §14.2 OTel
  span_id                 TEXT,
  parent_span_id          TEXT,
  gen_ai_system           TEXT,
  gen_ai_request_model    TEXT,
  gen_ai_response_model   TEXT,
  gen_ai_operation_name   TEXT,                                  -- 'chat' | 'embed'
  called_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status                  TEXT NOT NULL                          -- 'ok' | 'error' | 'rate_limited'
);
CREATE INDEX idx_token_usage_boss_time ON token_usage(boss_id, called_at DESC);
CREATE INDEX idx_token_usage_feature_time ON token_usage(feature, called_at DESC);
```

Web `/usage` chart từ bảng này (cost theo ngày, theo feature, theo
model, cache hit ratio).

## 7.8 Prompt registry

Prompts là **first-class entity trong DB** — không chôn trong file
code. Lý do: A/B test, hot-reload, rollback không deploy.

```sql
prompts (
  id          BIGSERIAL PRIMARY KEY,
  key         TEXT NOT NULL,                       -- 'note_update' | 'reminder_parse' | 'qa_with_search' | ...
  version     INTEGER NOT NULL,
  body        TEXT NOT NULL,                       -- Jinja2 template
  is_active   BOOLEAN NOT NULL DEFAULT FALSE,
  notes       TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by  INTEGER REFERENCES users(id),
  UNIQUE (key, version)
);
CREATE UNIQUE INDEX idx_prompts_active_per_key ON prompts(key) WHERE is_active;
```

Seed file `config/prompts/seed.yaml` load khi DB rỗng. Loader:

```python
async def get_prompt(key: str, version: int | None = None) -> str:
    if version is not None:
        return await prompts_repo.get(key, version)
    return await prompts_repo.get_active(key)
```

Workflow superadmin `/admin/prompts`:
- Editor body (Jinja2) + Notes (changelog)
- [Save as new version] [Set active] [Diff vs active] [Rollback]
- Version history với rollback button

A/B test Phase 1 (`prompt_ab_assignments` table — 2+ active version cùng
key, routing flag hash boss_id % 100).

DSPy auto-optimize Phase 2 (eval dataset đủ lớn → compile prompt auto).

## 7.9 Đã chốt & defer

**Đã chốt MVP:**
- `LLMGateway` Protocol + `NativeGateway` impl
- `models` DB + seed file; CRUD `/admin/models`
- `llm_routes` DB (condition_cel + fallback_chain + weight) — nâng từ flat feature_routing
- 3 model slot per sếp (smart / fast / vision)
- `feature_budgets` DB cho token budget + trim policy + compression
- **Prompt caching bật ngay MVP** qua stable prefix structure + `cache_prefix_hint`
- `prompts` DB + seed; CRUD `/admin/prompts`; version + rollback
- `token_usage` thêm cột `tokens_cached`, `cost_saved_cache_usd`, OTel fields

**Defer Phase 1+:**
- `LiteLLMGateway`, `PortkeyGateway` (interface sẵn)
- Web UI cho `llm_routes`, `feature_budgets`
- A/B routing weight (cột sẵn, MVP weight=100)
- LLMLingua compressor (slot sẵn)
- DSPy auto-optimize prompt (Phase 2)
- Streaming response (channel Zalo capability sau spike)
