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
| **DOCX / XLSX extract** | python-docx + openpyxl | Port legacy |
| **Channel — Zalo** | `zlapi-py` (port legacy) — acc cá nhân, không phải OA | OA defer; legacy code đã có session/cookie flow |
| **Channel — Telegram** | python-telegram-bot v21+ | Async, mature |
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
│   ├── base.py                # ChannelAdapter, InboundMessage, OutboundMessage protocols
│   ├── capabilities.py        # capability flags (§2.1.1)
│   ├── zalo.py                # zlapi-py adapter, poll loop, multi-account
│   ├── telegram.py
│   └── (messenger/whatsapp Phase 1+)
│
├── bot_accounts/              # quản lý pool bot acc
│   ├── manager.py             # load credentials, assign, status update
│   ├── zalo_session.py        # cookie / QR login flow
│   └── telegram_session.py
│
├── router.py                  # event → operation routing
│
├── repositories/              # DB access, all async
│   ├── users.py
│   ├── account_links.py
│   ├── bot_accounts.py
│   ├── bot_account_assignments.py
│   ├── messages.py
│   ├── group_notes.py
│   ├── outbound_messages.py
│   ├── boss_integrations.py
│   ├── reminders.py
│   ├── media_cache.py
│   ├── models.py              # ModelRegistry DB
│   ├── feature_routing.py
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
│   ├── reminder_firer.py      # §13
│   ├── subscription_check.py
│   ├── bot_account_health.py  # ping bot acc, mark logged_out/rate_limit
│   └── (Phase 1 jobs)

├── security/                  # §12 — hooks layer
│   ├── rate_limit.py          # RateLimiter interface (in-mem now, Redis later)
│   ├── csrf.py
│   ├── webhook_verify.py      # HMAC per provider
│   └── log_redact.py          # PII redact filter
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
# Zalo: credentials per-bot-account lưu trong DB (Fernet encrypted),
# không có env var. Telegram bot token cũng vậy — đẩy vào bot_accounts.
# Env chỉ giữ secret platform-wide.
LARK_APP_ID=...                   # Phase 1 (Lark Base plugin)
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

## 10.6 Đã chốt & defer

- 1 VPS MVP, split web/worker khi >50 sếp.
- Multi-region defer (SG/Singapore khi cần latency thấp).
- Backup pg_dump cron daily lên S3-compatible → setup ngày 1, chi tiết bucket key + retention defer.

## 10.7 Migration discipline

Đã có cú đau với migration đồng bộ thiếu → schema dịch nhưng data
chưa đồng bộ → lỗi runtime. Quy tắc cứng:

### 7-step checklist mỗi migration

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

- Memory: `feedback_db_migration_discipline` (7-step checklist legacy).
- Memory: `feedback_no_ad_hoc_db_mutations` — không DELETE/DROP ad-hoc
  trên prod; schema change đi qua migration.
