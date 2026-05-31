[← Index](./README.md)

# §7. LLM abstraction

## 7.1 Interface

```python
class LLMClient(ABC):
    async def chat(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> ChatResponse: ...

    async def embed(
        self,
        texts: list[str],
        model: str,
    ) -> list[list[float]]: ...
```

3 implementation:
- `OpenAICompatibleClient(base_url, api_key)` — cover OpenAI, Groq,
  OpenRouter, DeepSeek, Cerebras, Fireworks, Together, xAI, Ollama, vLLM
- `AnthropicClient(api_key)` — schema khác (system prompt, tool_use)
- `GeminiClient(api_key)` — schema khác

## 7.2 ModelRegistry — DB + seed file

Nguồn dữ liệu **vừa file vừa DB**:
- `config/models.yaml` = seed mặc định khi setup mới.
- Bảng `models` trong DB = source of truth runtime.
- Startup: nếu bảng rỗng → load seed. Sau đó DB override.

Schema:

```sql
models (
  id                       BIGSERIAL PRIMARY KEY,
  name                     TEXT NOT NULL,
  provider                 TEXT NOT NULL,                  -- 'openai' | 'groq' | 'anthropic' | 'gemini' | 'custom'
  endpoint_kind            TEXT NOT NULL,                  -- 'openai_compat' | 'anthropic' | 'gemini'
  base_url                 TEXT,
  tier                     TEXT NOT NULL,                  -- 'smart' | 'fast'
  ctx_max                  INTEGER NOT NULL,
  capabilities             JSONB NOT NULL DEFAULT '[]',    -- ['tool_use', 'vision', 'json_mode']
  cost_per_1m_input_usd    NUMERIC(10, 4),
  cost_per_1m_output_usd   NUMERIC(10, 4),
  is_platform_default      BOOLEAN NOT NULL DEFAULT FALSE, -- có dùng cho sếp chưa config?
  is_active                BOOLEAN NOT NULL DEFAULT TRUE,
  notes                    TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (provider, name)
);
```

Seed `config/models.yaml`:

```yaml
- name: gpt-4o-mini
  provider: openai
  endpoint_kind: openai_compat
  base_url: https://api.openai.com/v1
  tier: smart
  ctx_max: 128000
  capabilities: [tool_use, json_mode, vision]
  cost_per_1m_input_usd: 0.15
  cost_per_1m_output_usd: 0.60
  is_platform_default: true

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

- name: claude-haiku-4-5
  provider: anthropic
  endpoint_kind: anthropic
  tier: smart
  ctx_max: 200000
  capabilities: [tool_use, vision]
  cost_per_1m_input_usd: 1.00
  cost_per_1m_output_usd: 5.00
```

Superadmin CRUD qua `/admin/models` ([§9.3](./09-web-admin.md#93-sitemap-superadmin-pages)).
Sếp chọn model qua `/settings/ai` chỉ từ pool `is_active=true`. Nếu sếp
chưa config → fallback sang `is_platform_default` cùng tier.

## 7.3 Router & feature routing

Router không quyết theo `op` mà theo `feature` — đơn vị nhỏ hơn op (1 op
có thể gọi nhiều feature). Mapping feature → tier giữ trong DB để
superadmin chỉnh được mà không deploy code.

### 3 tier model

Sếp config **3 slot** ở `/settings/ai`:

| Tier | Vai trò | Đặc tính cần | Ví dụ model |
|---|---|---|---|
| **smart** | Reasoning, generation dài, structured output | tool_use, ctx ≥64k | gpt-4o, claude-haiku-4-5, gemini-2-pro |
| **fast** | Latency thấp, cost-sensitive, output ngắn | tool_use, latency <2s | llama-3.3-70b (groq), gpt-4o-mini |
| **vision** | Xử lý ảnh (capture extract, Q&A ảnh) | `vision` capability, fast-tier | gpt-4o-mini, gemini-flash, claude-haiku |

Mỗi tier có thể trỏ về cùng model (vd dùng gpt-4o-mini cho cả fast +
vision) — không bắt buộc 3 model khác nhau.

### Schema

```sql
feature_routing (
  feature      TEXT PRIMARY KEY,            -- 'note_update' | 'image_extract' | ...
  default_tier TEXT NOT NULL,               -- 'smart' | 'fast' | 'vision'
  description  TEXT,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Cột mới trong `users` (hoặc bảng `boss_ai_config` tách riêng):

```sql
ALTER TABLE users ADD COLUMN smart_model_id  BIGINT REFERENCES models(id);
ALTER TABLE users ADD COLUMN fast_model_id   BIGINT REFERENCES models(id);
ALTER TABLE users ADD COLUMN vision_model_id BIGINT REFERENCES models(id);
ALTER TABLE users ADD COLUMN api_keys_enc    BYTEA;   -- Fernet, JSON {provider: key}
```

### Seed feature_routing

| feature | tier | giải thích |
|---|---|---|
| `note_update` | smart | rebuild markdown dài, structured |
| `quick_ack` | fast | "vâng", "đã ghi" — latency UX |
| `intent_classify` | fast | JSON ngắn |
| `qa_with_search` | smart | reasoning đa nguồn |
| `summarize_group` | smart | structured + dài |
| `summarize_cross_group` | smart | đa group |
| `action_item_extract` | fast | nhiều call, cost-sensitive |
| `reminder_parse` | fast | structured ngắn |
| `url_summarize` | smart | reasoning sau khi extract |
| `image_extract` | **vision** | capture ảnh: describe + OCR |
| `image_qa` | **vision** | sếp `@bot ảnh này nói gì` |
| `dm_general` | smart | trợ lý cá nhân |

### Pick logic

```python
def pick_model(boss: Boss, feature: str, required_caps: list[str] = ()) -> Model:
    tier = feature_routing_repo.get(feature) or "smart"
    chosen_id = {
        "smart":  boss.smart_model_id,
        "fast":   boss.fast_model_id,
        "vision": boss.vision_model_id,
    }[tier]
    if chosen_id is None:
        # Fallback ladder: vision → smart (nếu smart có vision capability)
        # → platform default cùng tier
        if tier == "vision" and has_cap(boss.smart_model_id, "vision"):
            chosen_id = boss.smart_model_id
        else:
            chosen_id = platform_default_repo.get(tier=tier).id
    return resolve_capability(chosen_id, required_caps, boss)
```

Sếp không config slot nào → fallback platform default cùng tier. Vision
fallback đặc biệt: nếu sếp đã có smart model có vision → dùng smart làm
vision (slot vision không bắt buộc config).

## 7.4 Capability gap fallback

Khi feature yêu cầu capability mà model tier chọn không có:

```python
def resolve_capability(model_id: int, required: list[str], boss: Boss) -> Model:
    m = registry.get(model_id)
    missing = set(required) - set(m.capabilities)
    if not missing:
        return m
    # Try other slots: vision → smart → fast (theo capability có)
    for candidate_id in [boss.vision_model_id, boss.smart_model_id, boss.fast_model_id]:
        if candidate_id and not (set(required) - set(registry.get(candidate_id).capabilities)):
            log.warn(f"capability fallback {m.name} → {registry.get(candidate_id).name} ({missing})")
            return registry.get(candidate_id)
    raise CapabilityMissing(required, m.name)
```

Cảnh báo trên web khi save `/settings/ai`: vd "Smart model anh chọn
không có vision capability; ảnh sẽ dùng Vision model anh chọn ở slot
riêng. Nếu Vision slot trống, hệ thống dùng default platform."

## 7.5 Cost tracking

Mỗi LLM call:

```sql
token_usage (
  id           BIGSERIAL PRIMARY KEY,
  boss_id      INTEGER NOT NULL REFERENCES users(id),
  operation    TEXT NOT NULL,        -- 'note_update' | 'in_group' | 'dm' | 'embed'
  provider     TEXT NOT NULL,
  model        TEXT NOT NULL,
  tokens_in    INTEGER NOT NULL,
  tokens_out   INTEGER NOT NULL,
  cost_usd     NUMERIC(10, 6) NOT NULL,
  latency_ms   INTEGER NOT NULL,
  called_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status       TEXT NOT NULL          -- 'ok' | 'error' | 'rate_limited'
);
CREATE INDEX idx_token_usage_boss_time ON token_usage(boss_id, called_at DESC);
```

Web `/usage` chart từ bảng này (cost theo ngày, theo op, theo model).

## 7.6 Prompt registry

Prompts là **first-class entity trong DB** — không chôn trong file code.
Lý do: A/B test, hot-reload, rollback không deploy. Tham khảo Langfuse
prompt management + DSPy "prompts as code" approach.

### Schema

```sql
prompts (
  id          BIGSERIAL PRIMARY KEY,
  key         TEXT NOT NULL,                       -- 'note_update' | 'reminder_parse' | 'qa_with_search' | ...
  version     INTEGER NOT NULL,                    -- bump khi save mới
  body        TEXT NOT NULL,                       -- Jinja2 template
  is_active   BOOLEAN NOT NULL DEFAULT FALSE,      -- chỉ 1 version active/key (UNIQUE partial index)
  notes       TEXT,                                -- changelog ngắn
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by  INTEGER REFERENCES users(id),        -- superadmin uid
  UNIQUE (key, version)
);
CREATE UNIQUE INDEX idx_prompts_active_per_key ON prompts(key) WHERE is_active;
```

Seed file `config/prompts/seed.yaml` load lần đầu khi DB rỗng — tương
tự `models` (§7.2).

### Sử dụng trong code

```python
# Loader
async def get_prompt(key: str, version: int | None = None) -> str:
    if version is not None:
        return await prompts_repo.get(key, version)
    return await prompts_repo.get_active(key)

# In handler:
template = await get_prompt("note_update")
system_msg = Template(template).render(template_descriptor=..., note=..., delta=...)
```

### Workflow superadmin

`/admin/prompts` page ([§9.3](./09-web-admin.md#93-sitemap-superadmin-pages)):

```
┌────────────────────────────────────────────────────────────────┐
│ Prompts                                                         │
├────────────────────────────────────────────────────────────────┤
│ key                  │ active │ versions │ last edit            │
│ note_update          │ v7     │ 7        │ 2026-05-30 by admin  │
│ reminder_parse       │ v3     │ 3        │ 2026-05-22 by admin  │
│ qa_with_search       │ v12    │ 12       │ 2026-05-29 by admin  │
│ image_extract        │ v2     │ 2        │ 2026-05-31 by admin  │
└────────────────────────────────────────────────────────────────┘

Click row → editor:
  - Body (textarea với syntax highlight Jinja2)
  - Notes (changelog)
  - [Save as new version]  [Set active]  [Diff vs active]
  - Version history với rollback button
```

### A/B test (Phase 1)

Bảng `prompt_ab_assignments` (Phase 1) cho phép 2+ active version cùng
key với routing flag (vd hash boss_id % 100 < 30 → version A). MVP chỉ
1 active/key.

### DSPy auto-optimize (Phase 2)

Khi có eval dataset đủ lớn → DSPy compile prompt auto. MVP chỉ manual
edit + version. Foundation đã có (prompts trong DB) nên Phase 2 free.

## 7.7 Đã chốt & defer

- Model registry: DB + seed file. Superadmin CRUD qua `/admin/models`.
- Feature routing trong DB, edit được runtime.
- **Prompt registry: DB + seed file. Superadmin CRUD `/admin/prompts`. Version + rollback. A/B test Phase 1. DSPy auto Phase 2.**
- Streaming response → defer (channel SDK support tricky, Zalo personal không hỗ trợ).
- Prompt caching (Anthropic/OpenAI) → Phase 2 khi đo cost thật.
