[← Index](./README.md)

# §10. Tech stack & infrastructure

## 10.1 Stack

| Layer | Chọn | Lý do |
|---|---|---|
| **Language** | Python 3.12+ | Ecosystem AI/LLM, team đã quen |
| **Backend framework** | FastAPI | Async-first, OpenAPI sẵn, share với web admin |
| **DB driver** | asyncpg | Fastest async Postgres driver |
| **ORM** | None (SQL raw qua repositories) | Tránh ORM ma thuật, query rõ ràng |
| **Migration** | Alembic | Chuẩn Python |
| **Vector DB** | Qdrant 1.x (Docker) | Đã quen, scale tốt |
| **Embed model** | text-embedding-3-small (1536d) | Cân bằng cost/chất lượng |
| **URL fetch** | httpx + trafilatura | Extract content sạch (port legacy) |
| **YouTube transcript** | yt-dlp | Auto-caption (port legacy) |
| **PDF extract** | pypdf | Port legacy |
| **DOCX / XLSX extract** | python-docx (hoặc mammoth) + openpyxl | Port legacy |
| **Image processing** | Pillow + pillow_heif | HEIC → JPEG cho iPhone-via-Zalo (port legacy) |
| **Image extract-once** | Vision-LLM call (slot vision) | 1 call/ảnh lúc capture; save `media_text` |
| **Channel — Zalo** (MVP) | `zca-js@^2.1` Node bridge (port từ `archive/legacy:src/channels/zalo_bridge`, adapt v2 API — xem [spike](../../spikes/2026-05-31-zalo-2026-readiness.md)) — acc cá nhân, dual-mode (platform pool + boss-owned) | OA defer; QR login + session reconnect verified; legacy `zlapi-py` REJECTED (phone+password = bot flag) |
| **Channel — Telegram** (Phase 1) | python-telegram-bot v21+ | Khách hiện tại không dùng → defer; thư viện sẵn sàng khi cần |
| **Auth — Google OAuth** | Authlib | Maintained, async |
| **Password hash** | bcrypt (passlib) | Standard |
| **Encryption (token blob)** | cryptography (Fernet) | Symmetric, key trong env |
| **Web template** | Jinja2 | Built-in FastAPI |
| **Web interaction** | HTMX | Server-rendered + partial update |
| **CSS** | Tailwind CSS | Utility-first |
| **Charts** | Chart.js | Light, đủ cho dashboard |
| **Scheduler** | APScheduler (async) | Cron + interval, in-process |
| **Logging** | structlog → JSON | Easy parse |
| **Settings** | pydantic-settings | Type-safe env loading |
| **Test** | pytest + pytest-asyncio | Standard |

## 10.2 Project structure

Layering nguyên tắc (xem [§15.1](./15-agent-dispatch-extension.md#151-nguyên-tắc-cứng)):

- **domain/**: entity dataclass, value object, không I/O
- **repositories/**: I/O DB thuần, trả entity (không trả dict raw)
- **services/**: business logic — gọi repos + memory + retrieval + LLM
- **agents/**: operation = capability bundle (declarative, §15.2)
- **web/schemas/**: DTO request/response (tách khỏi domain entity)

Mọi extension point (operation, tool, memory provider, retrieval stage,
LLM gateway, trigger, media adapter, resolver) có registry riêng,
decorator declare. Add impl = drop file, không sửa core.

```
src/
├── main.py                    # FastAPI app factory + lifespan
├── config.py                  # pydantic-settings
├── container.py               # DI: build providers, register repos/services
│
├── domain/                    # entity dataclass + value object (không I/O)
│   ├── boss.py
│   ├── message.py
│   ├── group_note.py
│   ├── bot_account.py
│   ├── reminder.py
│   ├── memory.py              # Memory dataclass + MemoryScope enum
│   └── ...
│
├── channels/                  # inbound + outbound per channel
│   ├── base.py                # ChannelAdapter, InboundMessage, OutboundMessage protocols
│   ├── capabilities.py        # capability flags (§2.1.1)
│   ├── zalo.py                # zlapi-py adapter, poll loop, dual-mode bot acc
│   └── (telegram / messenger / whatsapp Phase 1+)
│
├── bot_accounts/              # quản lý bot acc (platform pool + boss-owned)
│   ├── manager.py
│   ├── ownership.py
│   ├── zalo_session.py
│   └── (telegram_session.py Phase 1+)
│
├── events/                    # in-process EventBus (§14)
│   ├── bus.py                 # InMemoryEventBus impl
│   ├── schema.py              # Pydantic event payload models + version field
│   └── subscribers/           # declared via @subscribe decorator
│
├── agents/                    # operation = capability bundle (§15.2)
│   ├── base.py                # Operation Protocol, @operation decorator
│   ├── registry.py            # OperationRegistry — auto-scan
│   ├── dispatcher.py          # EventBus → op dispatcher (§15.3, ~30 dòng)
│   ├── context.py             # build_context(deps_type, event) — DI
│   ├── triggers.py            # @trigger decorator + Debounce/Threshold (§15.8)
│   ├── note_updater.py
│   ├── in_group_responder.py
│   ├── dm_responder.py
│   └── reminder_firer.py
│
├── tools/                     # tool registry — unify core + plugin (§15.4)
│   ├── base.py                # @tool decorator, ToolSpec, ToolContext, ToolResult
│   ├── registry.py            # auto-scan src/tools/core/ + plugins/*/tools.py
│   ├── dispatcher.py          # call(tool, args, ctx) + parallel batch
│   └── core/
│       ├── search.py          # search_history, find_exact_quote
│       ├── notes.py           # read/edit/refresh_group_note, pin/unpin
│       ├── action_items.py
│       ├── reminders.py
│       ├── memory.py          # remember / forget → MemoryProvider.write / forget
│       ├── meta.py            # list_groups, current_time
│       └── web.py             # fetch_url
│
├── memory/                    # MemoryProvider Protocol (§15.5)
│   ├── base.py                # MemoryProvider Protocol, MemoryScope
│   ├── internal.py            # InternalMemoryProvider (MVP) — memory_entries
│   ├── reflective.py          # nightly episodic → semantic compaction (Phase 1)
│   └── (mem0.py / letta.py Phase 1)
│
├── retrieval/                 # pipeline + stages (§15.6, §5.3)
│   ├── base.py                # Retriever, RetrievalStage Protocol
│   ├── pipeline.py            # RetrievalPipeline — assemble stages từ DB config
│   └── stages/
│       ├── bm25.py            # BM25Retriever (Postgres FTS)
│       ├── dense.py           # DenseRetriever (Qdrant)
│       ├── fanout.py          # ParallelFanout combinator
│       ├── rrf.py             # RRFFuser
│       ├── mmr.py             # MMRDeduper
│       └── (cross_encoder.py / colbert.py Phase 1)
│
├── llm/                       # LLMGateway abstraction (§15.7, §7)
│   ├── base.py                # LLMGateway Protocol, LLMRequest, LLMResponse
│   ├── native.py              # NativeGateway (MVP) — wraps 3 clients + routing
│   ├── clients/
│   │   ├── openai_compat.py
│   │   └── gemini.py
│   ├── registry.py            # ModelRegistry — DB-backed
│   ├── routes.py              # llm_routes resolver + fallback ladder
│   ├── budget.py              # feature_budgets resolver + trim + compression
│   ├── cache_hint.py          # prompt caching prefix structuring
│   └── (litellm.py / portkey.py Phase 1+)
│
├── media/                     # media adapter registry (§15.9, §5.4)
│   ├── base.py                # MediaAdapter Protocol, @media_adapter decorator
│   ├── registry.py
│   └── adapters/
│       ├── web.py             # URL + YouTube + TikTok
│       ├── document.py        # PDF + DOCX + XLSX
│       └── image.py           # HEIC + vision-LLM extract-once
│
├── resolvers/                 # chain-of-responsibility resolvers (§15.10)
│   ├── group_owner.py
│   ├── scope.py               # reminder scope
│   └── chat_type.py
│
├── services/                  # business logic layer
│   ├── note_service.py        # update note (debounce, lock, version, action_item sync)
│   ├── reminder_service.py
│   ├── boss_service.py
│   ├── plugin_service.py
│   └── ...
│
├── repositories/              # DB I/O — return domain entities
│   ├── base.py                # BossScopedRepo (constructor-injected boss_id, §12.6)
│   ├── users.py
│   ├── account_links.py
│   ├── bot_accounts.py
│   ├── bot_account_assignments.py
│   ├── messages.py
│   ├── group_notes.py
│   ├── note_templates.py
│   ├── outbound_messages.py
│   ├── boss_integrations.py
│   ├── reminders.py
│   ├── pins.py
│   ├── media_cache.py
│   ├── memory_entries.py
│   ├── models.py              # ModelRegistry DB
│   ├── prompts.py
│   ├── llm_routes.py          # §7.3
│   ├── feature_budgets.py     # §7.6
│   ├── retrieval_pipelines.py # §15.6
│   ├── agent_triggers.py      # §15.8
│   ├── payments.py
│   ├── token_usage.py         # OTel-named fields (§14.2)
│   └── tool_call_log.py
│
├── prompts/                   # prompt loader (§7.8)
│   └── loader.py              # prompts_repo.get_active(key) + Jinja2 render
│
├── plugins/                   # workspace cho plugin dirs (3rd-party Phase 2)
│   └── (rỗng ở Phase 0)
│
├── web/
│   ├── schemas/               # Pydantic DTO request/response (tách khỏi domain)
│   │   ├── boss.py
│   │   ├── reminder.py
│   │   └── ...
│   ├── routes/
│   │   ├── app.py             # user pages
│   │   ├── admin.py           # superadmin pages
│   │   ├── api.py             # JSON endpoints cho HTMX
│   │   └── oauth.py
│   ├── templates/
│   ├── static/
│   └── deps.py                # session, role gate, BossContext factory
│
├── scheduler/                 # APScheduler jobs
│   ├── note_flush.py
│   ├── reminder_firer.py      # publish reminder.due event
│   ├── subscription_check.py
│   ├── bot_account_health.py
│   └── (Phase 1 jobs)
│
├── security/                  # §12
│   ├── rate_limit.py
│   ├── csrf.py
│   ├── webhook_verify.py
│   └── log_redact.py
│
├── infra/                     # external client wrappers
│   ├── db.py                  # asyncpg pool factory
│   ├── qdrant.py
│   └── observability.py
│
└── utils/
    ├── dates.py
    ├── crypto.py              # Fernet
    ├── text.py
    └── markdown.py

migrations/                    # Alembic
config/
├── models.yaml                # ModelRegistry seed
├── llm_routes.yaml            # llm_routes seed (§7.3)
├── feature_budgets.yaml       # feature_budgets seed (§7.6)
├── retrieval_pipelines.yaml   # retrieval_pipelines seed (§15.6)
├── agent_triggers.yaml        # agent_triggers seed (§15.8)
└── prompts/                   # prompts seed (Jinja2)
tests/
├── unit/
├── integration/
└── fixtures/                  # production-snapshot fixtures (§10.7 step 8)
docker/
├── docker-compose.yml         # dev: postgres + qdrant + app
└── Dockerfile
pyproject.toml
```

### Pattern rules

1. **Repository layer trả domain entity, không trả dict.** Cấm
   `r["boss_id"]` access ở caller. Add cột mới = update entity dataclass
   + repo mapping; caller code không sửa.
2. **Repository nhận `BossContext` qua constructor**, không nhận
   `boss_id` lẻ trong method. Compiler-enforced (mypy strict) — không
   bypass authz boundary (§12.6).
3. **Cấm `db.py` free-function** (`db.fetch(...)` module-level). Mọi
   DB access đi qua repository instance. Memory `feedback_db_migration_discipline`.
4. **Service gọi repository, agent gọi service.** Agent handler không
   gọi repository trực tiếp — dễ test mock + boundary rõ.
5. **Web layer dùng DTO Pydantic** ở `web/schemas/`, không expose
   domain entity ra response trực tiếp (tránh leak field nhạy cảm).

## 10.3 Deployment (MVP)

```
┌─────────────────────────────────────────────────┐
│  1 VPS (Ubuntu 22+, 4 vCPU / 8 GB RAM đủ đầu)  │
│                                                 │
│  Docker Compose:                                │
│   - app           (FastAPI, port 80/443)        │
│   - postgres:16   (port 5432, volume)           │
│   - qdrant:1.x    (port 6333, volume)           │
│                                                 │
│  Reverse proxy: Caddy (auto HTTPS)              │
│  Domain: app.botname.com → app                  │
└─────────────────────────────────────────────────┘
```

Khi scale (>50 sếp, LLM cost cao): tách Qdrant ra VPS riêng, app chạy
multi-instance sau load balancer.

## 10.4 Env config

`.env`:

```bash
# DB
POSTGRES_DSN=postgres://user:pass@localhost:5432/groupnote
QDRANT_URL=http://localhost:6333

# Auth
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
SESSION_SECRET=<random 64 bytes>
FERNET_KEY=<base64 32 bytes>           # for token blob encryption
OAUTH_REDIRECT_WHITELIST=https://app.botname.com/api/oauth/google/callback,https://app.botname.com/api/oauth/plugin/lark_base/callback

# Superadmin
SUPERADMIN_EMAILS=tranvuongquocdat@gmail.com

# Platform LLM (cho free trial / fallback khi sếp chưa BYO key)
# MVP defaults: smart + vision = OpenAI gpt-4o-mini, fast = Groq llama-3.3-70b
PLATFORM_OPENAI_API_KEY=<optional>
PLATFORM_GROQ_API_KEY=<optional>

# Channels
# Zalo: credentials per-bot-account lưu trong DB (Fernet encrypted),
# không có env var. Phase 1 Telegram bot token cũng vậy.
LARK_APP_ID=...                        # Phase 1 (Lark Base plugin)
LARK_APP_SECRET=...

# Subscription
BANK_ACCOUNT_NUMBER=...
BANK_ACCOUNT_NAME=...
BANK_BIN=...

# Cost cap
DEFAULT_BOSS_COST_CAP_USD_DAILY=5      # §12 — degrade smart→fast khi cap đụng
```

## 10.5 Observability

- **Logging**: structlog → JSON → stdout → `journalctl` hoặc file.
  Fields bắt buộc: `boss_id`, `feature`, `operation`, `provider`,
  `model`, `tokens_*`, `latency_ms`, `trace_id`, `span_id`, `request_id`.
- **Metrics**: `/metrics` endpoint format Prometheus. Key:
  - `messages_ingested_total{provider,boss_id}`
  - `note_updates_total{boss_id,status}`
  - `llm_calls_total{provider,model,status}`
  - `llm_call_latency_seconds{feature,tier}`
  - `llm_cache_hit_ratio{feature,model}` (§7.5)
  - `outbound_messages_total{channel,status}`
  - `retrieval_stage_latency_seconds{stage}` (§5.3)
- **Tracing**: OTel-aligned schema MVP (§14.2). Langfuse exporter Phase 1.
- **Health**: `/healthz` → `{status, db, qdrant}` cho monitor.

## 10.6 Đã chốt & defer

- 1 VPS MVP, split web/worker khi >50 sếp.
- Multi-region defer (SG/Singapore khi cần latency thấp).
- Backup pg_dump cron daily lên S3-compatible → setup ngày 1, chi tiết bucket key + retention defer.

## 10.7 Migration discipline

Đã có cú đau với migration đồng bộ thiếu → schema dịch nhưng data
chưa đồng bộ → lỗi runtime. Quy tắc cứng:

### 8-step checklist mỗi migration

1. **Forward + backward**: mỗi migration Alembic phải có `upgrade()` và
   `downgrade()`. Cấm `op.execute` raw mà không nghĩ rollback.
2. **Additive-first**: thêm cột → DEFAULT + NULLable; backfill ở step
   data migration; drop cũ ở migration sau (≥1 release gap).
3. **Data migration tách script**: nếu phải biến đổi data, viết
   `migrations/data/<id>_<name>.py` riêng (idempotent, có dry-run flag),
   không nhúng vào Alembic upgrade.
4. **Auto-gen disabled**: `alembic revision --autogenerate` chỉ dùng
   tham khảo diff, **không commit thẳng**. Mỗi migration người review.
5. **Preflight check**: trước khi apply prod —
   - count rows bảng affected trước
   - dry-run trên staging snapshot
   - sample diff (10 rows trước/sau)
   - rollback test: upgrade → downgrade → upgrade pass
6. **CI gate**: pipeline chạy `alembic upgrade head` trên DB staging
   snapshot mỗi PR. Fail = block merge.
7. **Drop sau ≥1 release**: cấm drop column / table cùng PR thêm cột
   thay thế. Tách 2 PR cách ≥1 release để rollback an toàn.
8. **Regression test from snapshot**: trước merge, chạy integration
   test suite trên **production snapshot sanitized** (`tests/fixtures/`).
   Fail nếu old behavior break — bắt được data drift, không chỉ schema.

### Backfill convention

```python
# migrations/data/0042_backfill_bot_account_assignments.py
"""Backfill assignments cho boss đã có account_links trước khi feature ra."""

DRY_RUN_DEFAULT = True

async def run(db, *, dry_run: bool = DRY_RUN_DEFAULT):
    rows = await db.fetch("SELECT boss_id, provider FROM account_links WHERE ...")
    n = 0
    for r in rows:
        bot_acc_id = await pick_least_loaded(db, r["provider"])
        if dry_run:
            print(f"would assign boss={r['boss_id']} provider={r['provider']} → {bot_acc_id}")
        else:
            await db.execute("INSERT INTO bot_account_assignments ...", ...)
        n += 1
    print(f"{'dry-run: ' if dry_run else ''}processed {n} rows")
```

Mọi backfill viết style trên: dry-run mặc định, idempotent (re-run OK),
output diff trước khi commit.

### Tham khảo

- Memory: `feedback_db_migration_discipline` (8-step checklist).
- Memory: `feedback_no_ad_hoc_db_mutations` — không DELETE/DROP ad-hoc
  trên prod; schema change đi qua migration.

## 10.8 Config classification — code vs DB

Quy tắc cứng cho mọi config (xem [§15.11](./15-agent-dispatch-extension.md#1511-config-classification--code-vs-db)):

| Đặc tính | Lưu ở | Vd |
|---|---|---|
| Có thể A/B test | **DB** | llm_routes, prompts |
| Có thể per-boss override | **DB** | smart/fast/vision model_id, feature_budgets per-boss (Phase 1) |
| Có thể hot-tune không deploy | **DB** | trigger debounce/threshold, retrieval pipeline stages |
| Cần seed default cho install mới | **DB** + seed file `config/*.yaml` | models, prompts, llm_routes, feature_budgets, retrieval_pipelines, agent_triggers |
| Code-only constant (struct, interface) | Code | Operation class, Tool decorator, Memory scope enum, Channel capability matrix |

**Bảng config DB bắt buộc seed MVP** (kể cả chưa có admin UI):
`models`, `prompts`, `llm_routes`, `feature_budgets`,
`retrieval_pipelines`, `agent_triggers`, `note_templates`.

Cache invalidation: admin sửa DB → publish event `registry.invalidated`
([§14.1](./14-performance-observability.md#141-eventbus-internal))
→ in-memory cache TTL 60s + immediate clear cho subscriber agent loop.

## 10.9 Test strategy

| Layer | Test kind | Vd |
|---|---|---|
| domain/ | unit (pure) | entity validation, value object equality |
| repositories/ | integration (real DB) | fixture từ production snapshot sanitized; assertEqual entity |
| services/ | unit + integration | mock repo + memory + LLM; test happy path + edge case |
| agents/ | integration | EventBus fake, MemoryProvider fake, LLMGateway stub; test op end-to-end |
| tools/ | unit | mock ToolContext; verify side effect |
| retrieval/, memory/, llm/ | unit + contract | Protocol contract test mọi impl |
| channels/ | e2e (record + replay) | fixture từ legacy probe; verify adapter ↔ InboundMessage shape |
| web/ | HTTP integration | TestClient FastAPI; verify DTO ↔ status code |

**Coverage target MVP**: 70% line, 80% trên `services/` + `agents/` (logic
core). `channels/` và `web/` coverage thấp hơn (e2e đắt).

**Fixture conventions**: `tests/fixtures/` chứa snapshot DB sanitized
(boss name, message text replaced; structure giữ). Reload mỗi suite
qua `tests/conftest.py:reset_db_to_fixture`. Snapshot bump khi schema
migration land — bắt được drift sớm.
