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
| **Voice STT** | OpenAI Whisper API (MVP) | Cost & latency |
| **URL fetch** | httpx + trafilatura | Extract content sạch |
| **Channel — Zalo** | Zalo OA HTTPS API + webhook | (không có Python SDK chính chủ) |
| **Channel — Telegram** | python-telegram-bot v21+ | Async, mature |
| **Channel — Lark Messenger** | lark-oapi SDK (Phase 1) | Official |
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

## 10.2 Project structure (đề xuất)

```
src/
├── main.py                    # FastAPI app factory + lifespan
├── config.py                  # pydantic-settings
├── container.py               # DI: build clients, register repos
│
├── channels/                  # inbound + outbound per channel
│   ├── base.py                # InboundMessage, OutboundMessage protocols
│   ├── zalo.py
│   ├── telegram.py
│   └── lark_msg.py            # (Phase 1)
│
├── router.py                  # event → operation routing
│
├── repositories/              # DB access, all async
│   ├── users.py
│   ├── account_links.py
│   ├── messages.py
│   ├── group_notes.py
│   ├── outbound_messages.py
│   ├── boss_integrations.py
│   ├── payments.py
│   └── token_usage.py
│
├── agent/                     # operation handlers
│   ├── note_updater.py
│   ├── in_group_responder.py
│   ├── dm_responder.py
│   ├── tools/                 # core tool implementations
│   │   ├── search.py
│   │   ├── notes.py
│   │   ├── action_items.py
│   │   └── ...
│   └── dispatcher.py          # tool registry + call
│
├── llm/                       # LLM abstraction
│   ├── base.py                # LLMClient interface
│   ├── openai_compat.py
│   ├── anthropic.py
│   ├── gemini.py
│   ├── registry.py            # ModelRegistry
│   └── router.py              # pick_model
│
├── plugins/                   # workspace cho plugin dirs
│   └── (rỗng ở Phase 0)
│
├── web/
│   ├── routes/
│   │   ├── app.py             # user pages
│   │   ├── admin.py           # superadmin pages
│   │   ├── api.py             # JSON endpoints cho HTMX
│   │   └── oauth.py           # callbacks (Google + plugin)
│   ├── templates/             # Jinja2
│   ├── static/                # CSS, JS, icons
│   └── deps.py                # session, role gate
│
├── scheduler/                 # APScheduler jobs
│   ├── note_flush.py
│   ├── subscription_check.py
│   └── (Phase 1 jobs)
│
├── infra/                     # external client wrappers
│   ├── db.py                  # asyncpg pool factory
│   ├── qdrant.py
│   └── observability.py
│
└── utils/
    ├── dates.py
    ├── crypto.py              # Fernet
    ├── text.py                # diacritic normalize, ...
    └── markdown.py            # render group note section-skip-empty

migrations/                    # Alembic
config/
├── models.yaml                # ModelRegistry
└── prompts/                   # Long prompt templates (Jinja2)
tests/
├── unit/
└── integration/
docker/
├── docker-compose.yml         # dev: postgres + qdrant + app
└── Dockerfile
pyproject.toml
```

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
FERNET_KEY=<base64 32 bytes>      # for token blob encryption

# Superadmin
SUPERADMIN_EMAILS=tranvuongquocdat@gmail.com

# Platform LLM (cho free trial / fallback)
PLATFORM_OPENAI_API_KEY=<optional>

# Channels
ZALO_OA_ID=...
ZALO_OA_SECRET=...
ZALO_WEBHOOK_VERIFY=...
TELEGRAM_BOT_TOKEN=...
LARK_APP_ID=...                   # Phase 1
LARK_APP_SECRET=...

# Subscription (cho hiển thị VietQR)
BANK_ACCOUNT_NUMBER=...
BANK_ACCOUNT_NAME=...
BANK_BIN=...
```

## 10.5 Observability

- **Logging**: structlog → JSON → stdout → `journalctl` hoặc file.
  Fields bắt buộc: `boss_id`, `operation`, `provider`, `model`,
  `tokens_*`, `latency_ms`, `request_id`.
- **Metrics**: `/metrics` endpoint format Prometheus (in-process). Key:
  - `messages_ingested_total{provider,boss_id}`
  - `note_updates_total{boss_id,status}`
  - `llm_calls_total{provider,model,status}`
  - `llm_call_latency_seconds`
  - `outbound_messages_total{channel,status}`
- **Tracing**: defer Phase 2 (OpenTelemetry).
- **Health**: `/healthz` → `{status, db, qdrant}` cho monitor.

## 10.6 Mở

- **(mở) Multi-region** — server ở SG/Singapore cho latency Zalo
  webhook + LLM API. Defer.
- **(mở) Backup** — pg_dump cron daily lên S3-compatible. Defer chi tiết.
