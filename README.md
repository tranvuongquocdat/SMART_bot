# SMART_bot — Thư ký giám đốc ảo

Bot LLM hỗ trợ giám đốc quản lý task, nhân sự, dự án, lịch nhắc qua chat tự nhiên.  
Multi-tenant: mỗi sếp có workspace riêng, bot nhận biết ngữ cảnh tự động theo kênh + nhóm.

---

## Stack

| Layer | Công nghệ |
|-------|-----------|
| Backend | Python 3.12, FastAPI, asyncpg (PostgreSQL 16) |
| Vector store | Qdrant 1.12 (semantic memory + retrieval) |
| LLM | OpenAI-compatible endpoint, Google Gemini, Groq — routing theo feature/tier |
| Migrations | Alembic |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4, TanStack Query |
| Auth | Email/password + Google OAuth, session cookie, CSRF |
| Scheduler | APScheduler (reminder, review, deadline push) |
| Channels | Telegram (production), Zalo (demo), Web simulator (dev) |

---

## Tính năng

**Core (channel-agnostic):**
- **Action items** — CRUD task bằng ngôn ngữ tự nhiên, deadline push 24h / 2h / quá hạn
- **Reminders** — Đặt lịch nhắc, tùy chọn lặp lại, fire qua APScheduler
- **Group notes** — Tóm tắt hội thoại nhóm, cập nhật tự động theo lịch
- **Semantic memory** — Ghi/đọc bộ nhớ dài hạn qua Qdrant (tool: `remember` / `forget`)
- **Scheduled reviews** — Morning brief, evening summary, custom time
- **Multi-tier LLM routing** — Smart (reasoning), Fast (quick reply), Vision — chọn per-feature
- **Cost cap** — Giới hạn chi phí per-boss per-day; enforcement tự động
- **Plugin tools** — Scan thư mục `plugins/` khi khởi động, auto-register tool definitions

**Web UI:**

| Giao diện | Path | Yêu cầu |
|-----------|------|---------|
| Admin (sếp) | `/app/admin` | role = boss |
| Superadmin | `/app/superadmin` | role = superadmin |

Admin UI gồm: Dashboard, Groups (chat + notes + action items), Reminders, Projects, Channels, Usage, Subscription, Settings.

Superadmin UI gồm: LLM Models, Bot Accounts, User management, System Prompts, Note Templates, Agent Triggers, Audit Log, Retrieval Pipelines.

---

## Kênh nhắn tin

| Kênh | Trạng thái | Ghi chú |
|------|------------|---------|
| Telegram | ✅ Production | Long-poll, group + DM, @mention |
| Zalo | 🟡 Demo (1 account) | Node bridge qua QR login, DM + group |
| Web (simulator) | 🔧 Dev/testing | FastAPI WebSocket, giả lập multi-user group |

**Inbound flow:**  
Channel adapter → `IncomingMessage` → MessageRouter → Event bus → Operation handler (DM/Group) → LLM loop + tools → OutboundService → Channel adapter

---

## Cấu trúc code

```
src/
├── main.py              FastAPI app + lifespan (DB, Qdrant, channels, scheduler)
├── config.py            Pydantic Settings (đọc .env)
│
├── agents/              Operation handlers: dm_responder, in_group_responder,
│                          note_updater, reminder_firer
├── channels/            Provider abstraction; telegram, zalo, web simulator
├── controllers/         MessageRouter — inbound boundary
├── domain/              Pydantic models: Boss, Message, ActionItem, Reminder, …
├── events/              In-memory event bus (pub/sub)
├── llm/                 LLM gateway, model registry, provider adapters
├── memory/              Semantic/episodic memory via Qdrant
├── retrieval/           Retrieval pipeline: BM25, dense, MMR, RRF
├── repositories/        Data access (27 repos: users, messages, action_items, …)
├── services/            Domain services (outbound, scheduled review, reminders)
├── tools/               Agent-callable tools (15+): action_items, reminders, search,
│                          notes, memory ops, fetch_url, current_time
├── web/                 FastAPI routes: auth, admin API, superadmin API, SPA fallback
├── scheduler/           APScheduler jobs
├── security/            Rate limiting, CSRF, session, cost cap
├── media/               Media download + parse (trafilatura, yt-dlp, pypdf, pillow)
├── plugin_api/          Plugin interface
└── utils/               Text, dates, validation
```

```
frontend/src/
├── modules/admin/       Admin dashboard, groups, reminders, projects, channels, …
├── modules/superadmin/  Models, bot-accounts, bosses, prompts, audit-log, …
├── components/          AppShell, UserMenu, CommandPalette, DataTable
└── lib/                 API client, RBAC, auth hooks, theming
```

---

## Setup

### Yêu cầu

- Docker + Docker Compose (PostgreSQL, Qdrant)
- Python 3.12, Node 22, pnpm
- API keys: LLM provider (OpenAI-compatible / Gemini / Groq), Google OAuth (optional)

### Chạy local (uv)

```bash
# 1. Khởi động infrastructure
docker compose -f docker/docker-compose.yml up -d

# 2. Sync deps + chạy migrations
uv sync
uv run alembic upgrade head

# 3. Chạy backend
uv run uvicorn src.main:app --reload --port 8000

# 4. Build frontend (cần khi đổi UI)
bash scripts/build_frontend.sh

# 5. Tests
uv run pytest tests/ -v
```

### Biến môi trường quan trọng (`.env`)

```
POSTGRES_DSN=postgresql+asyncpg://smart:smart@localhost:5433/smart_bot
QDRANT_URL=http://localhost:6333

# LLM — dùng ít nhất 1 provider
OPENAI_API_KEY=...
GEMINI_API_KEY=...

# Auth
SECRET_KEY=...                  # random 32+ chars
GOOGLE_CLIENT_ID=...            # optional (OAuth)
GOOGLE_CLIENT_SECRET=...

# Channels
TELEGRAM_BOT_TOKEN=...
ZALO_ENABLED=false              # bật khi setup Zalo
```

### Docker Compose services

| Service | Image | Port host | Ghi chú |
|---------|-------|-----------|---------|
| postgres | postgres:16 | 5433 | user/pass/db = smart |
| qdrant | qdrant/qdrant:v1.12.4 | 6333 | REST API |

### Seed demo data

```bash
bash scripts/seed_demo.sh
```

---

## Quy trình onboard

1. Chạy hệ thống + seed (hoặc tạo superadmin thủ công qua DB).
2. Đăng nhập web UI tại `/login`.
3. Superadmin tạo bot account (Telegram token) trong `/app/superadmin/bot-accounts`.
4. Boss đăng nhập → vào `/app/admin/channels` → kết nối bot.
5. Tìm bot trên Telegram, nhắn bất kỳ → agent bắt đầu xử lý.
6. (Tuỳ chọn) Bật Zalo: `ZALO_ENABLED=true` trong `.env`, chạy `bash scripts/setup_zalo.sh` → quét QR.

---

## Bảo mật

- Mỗi boss hoàn toàn isolated trong database (row-level filtering theo boss_id).
- Session cookie signed (itsdangerous), TTL 30 ngày.
- CSRF: double-submit (cookie + header).
- Rate limiting: login 5 req/5min, OAuth callback 30 req/min, Zalo outbound per-thread spacing.
- Credentials kênh encrypt bằng Fernet trước khi lưu DB.
- Cost cap enforcement tự động; vượt cap → agent trả lỗi, không gọi LLM.
