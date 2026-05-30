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

## 7.2 ModelRegistry

File config `config/models.yaml`:

```yaml
- name: gpt-4o-mini
  provider: openai
  endpoint: openai_compat
  base_url: https://api.openai.com/v1
  tier: smart                                  # smart | fast
  ctx_max: 128000
  capabilities: [tool_use, json_mode, vision]
  cost_per_1m_input_usd: 0.15
  cost_per_1m_output_usd: 0.60

- name: llama-3.3-70b-versatile
  provider: groq
  endpoint: openai_compat
  base_url: https://api.groq.com/openai/v1
  tier: fast
  ctx_max: 128000
  capabilities: [tool_use]
  cost_per_1m_input_usd: 0.59
  cost_per_1m_output_usd: 0.79

- name: claude-haiku-4-5
  provider: anthropic
  endpoint: anthropic
  tier: smart
  ctx_max: 200000
  capabilities: [tool_use, vision]
  cost_per_1m_input_usd: 1.00
  cost_per_1m_output_usd: 5.00

# Thêm model mới = thêm row, không sửa code
```

Reload khi server start. Superadmin có thể thêm row qua web ở Phase 2.

## 7.3 Router & 2-tier routing

```python
def pick_model(boss: Boss, op: Operation) -> tuple[str, str]:
    """Returns (provider, model_name)."""
    tier = TIER_BY_OP[op]   # NoteUpdater→smart, ack→fast, Responder→smart, ...
    if tier == "smart":
        return boss.smart_provider, boss.smart_model
    return boss.fast_provider, boss.fast_model
```

Mỗi op trong code khai báo tier mặc định. Sếp config 2 model qua web;
nếu chỉ 1 model → cả 2 tier dùng cùng.

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

## 7.6 Mở

- **(mở) Streaming response** — bot reply có stream chunk được không?
  Cải UX cảm giác nhanh. Defer (channel SDK support tricky).
- **(mở) Prompt caching** (Anthropic, OpenAI) — giảm cost khi reuse
  system prompt. Phase 2.
