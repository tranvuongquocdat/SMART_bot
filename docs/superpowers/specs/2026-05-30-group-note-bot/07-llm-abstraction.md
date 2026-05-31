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

### Schema

```sql
feature_routing (
  feature      TEXT PRIMARY KEY,            -- 'note_update' | 'qa_with_search' | 'reminder_parse' | ...
  default_tier TEXT NOT NULL,               -- 'smart' | 'fast'
  description  TEXT,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Seed cho MVP (cũng là bảng [§6.5](./06-agent-layer.md#65-feature--tier-routing)):

| feature | tier |
|---|---|
| `note_update` | smart |
| `quick_ack` | fast |
| `intent_classify` | fast |
| `qa_with_search` | smart |
| `summarize_group` | smart |
| `summarize_cross_group` | smart |
| `action_item_extract` | fast |
| `reminder_parse` | fast |
| `url_summarize` | smart |
| `dm_general` | smart |

### Pick logic

```python
def pick_model(boss: Boss, feature: str, required_caps: list[str] = ()) -> Model:
    tier = feature_routing_repo.get(feature) or "smart"
    chosen = boss.smart_model if tier == "smart" else boss.fast_model
    if chosen is None:
        chosen = platform_default_repo.get(tier=tier)
    return resolve_capability(chosen, required_caps, boss)
```

Sếp config 2 model (smart + fast) qua `/settings/ai`. Chỉ chọn 1 model →
cả 2 tier dùng cùng. Không config → dùng platform default.

## 7.4 Capability gap fallback

Khi op yêu cầu capability mà model boss chọn không có:

```python
def resolve_capability(model_name: str, required: list[str], boss: Boss) -> str:
    caps = registry.get(model_name).capabilities
    missing = set(required) - set(caps)
    if not missing:
        return model_name
    # fallback theo priority: smart > vision > tool_use
    for candidate in [boss.smart_model, boss.vision_model_default]:
        cc = registry.get(candidate).capabilities
        if not (set(required) - set(cc)):
            log.warn(f"fallback {model_name} → {candidate} ({missing})")
            return candidate
    raise CapabilityMissing(required, model_name)
```

Vd: boss chọn Groq Llama 3.3 cho fast nhưng op cần vision → fallback
sang smart (gpt-4o).

Cảnh báo trên web khi save config: "Fast model không có vision → khi
xử lý ảnh sẽ tự fallback sang Smart model."

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

## 7.6 Đã chốt & defer

- Model registry: DB + seed file. Superadmin CRUD qua `/admin/models`.
- Feature routing trong DB, edit được runtime.
- Streaming response → defer (channel SDK support tricky, Zalo personal không hỗ trợ).
- Prompt caching (Anthropic/OpenAI) → Phase 2 khi đo cost thật.
