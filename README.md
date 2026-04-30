# AI Secretary — Thư ký giám đốc ảo

Bot LLM hỗ trợ giám đốc quản lý task, nhân sự, dự án, lịch nhắc qua chat tự nhiên.
Multi-workspace: một người có thể là sếp công ty A và đối tác công ty B — bot tự nhận biết ngữ cảnh.

---

## Tình trạng hiện tại

**Channels (kênh nhắn tin):**

| Kênh | Trạng thái | Ghi chú |
|------|------------|---------|
| Telegram | ✅ Production | Long-poll, group + DM, group admin ops |
| Zalo | 🟡 Demo (1 account) | QR login, DM + group, send/receive — chưa có rate-limit/multi-account |
| Messenger / WhatsApp / Web | ⏳ Roadmap | Channel layer đã trừu tượng hóa (`src/channels/base.py`) |

**Tính năng cốt lõi (channel-agnostic):**

- **Tasks** — CRUD bằng tự nhiên, search ngữ nghĩa (Qdrant), approval flow, deadline push (24h / 2h / quá hạn).
- **People** — CRUD nhân sự, kiểm tra workload, phân loại member / partner / customer.
- **Multi-workspace** — Mỗi sếp 1 Lark Base riêng (6 bảng); join request có duyệt.
- **Reminders** — Đặt giờ, sync 2 chiều với Lark.
- **Scheduled review** — `morning_brief`, `evening_summary`, `custom`; tuỳ chỉnh giờ.
- **Group** — Lưu mọi tin nhắn, chỉ trả lời khi `@mention`.
- **Advisor mode** — Tự chuyển sang chế độ tư vấn cho phân tích phức tạp.
- **Reset workspace** — 2 bước xác nhận, xóa Lark Base.

---

## Setup

### Yêu cầu

- Docker + Docker Compose, hoặc Python 3.12 + Node 22 (cho dev local)
- Telegram Bot Token, Lark App, OpenAI key, Cohere key

### Chạy nhanh (Docker)

```bash
cp .env.example .env       # điền các API keys vào
docker compose up -d --build
docker compose logs -f
```

### Dev local (uv)

```bash
uv sync                                          # install deps + tạo .venv
uv run uvicorn src.main:app --port 8000          # khởi chạy
uv run pytest tests/ -v                          # chạy tests
```

### Bật Zalo channel

```bash
# 1. Login lần đầu (host)
cd src/channels/zalo_bridge
npm install
node login.js                                    # quét QR → session.json

# 2. Bật trong .env
echo "ZALO_ENABLED=true" >> ../../../.env

# 3. (Docker) — copy session vào volume
mkdir -p data/zalo && cp src/channels/zalo_bridge/session.json data/zalo/
# rồi set ZALO_SESSION_PATH=data/zalo/session.json trong .env
```

---

## Cấu trúc code

```
src/
├── main.py                  FastAPI lifespan: init clients, build container, start channels
├── container.py             AppContainer (DI snapshot, frozen)
├── config.py                Settings (pydantic-settings, đọc .env)
├── db.py                    Facade trên SQLite (aiosqlite)
├── scheduler.py             APScheduler: review, deadline push, reminder fire
├── identity.py              Resolve provider+external_id → internal UUID
├── context.py / context_builder.py    Build context cho LLM
│
├── agent/                   LLM loop + tool dispatch
│   ├── secretary_agent.py     Tool-using loop
│   ├── advisor_agent.py       Read-only analysis
│   ├── onboarding_agent.py    Đăng ký sếp / join company
│   ├── reminder_agent.py      Render reminder text
│   ├── tool_dispatcher.py     Tool registry + execution
│   └── tool_definitions.py    Schemas
│
├── channels/                Provider abstraction (Messenger Protocol)
│   ├── base.py                IncomingMessage / OutgoingMessage / capabilities
│   ├── registry.py            provider → messenger map
│   ├── telegram.py            TelegramMessenger
│   ├── telegram_singleton.py  Legacy shim, dispatch theo provider
│   └── zalo_bridge/           Zalo (demo)
│       ├── bridge.js            Long-running JSONL bridge ↔ zca-js
│       ├── login.js             QR login → session.json
│       ├── package.json         zca-js dep
│       ├── process.py           ZaloBridgeProcess (async subprocess + JSONL)
│       └── ...
│   └── zalo.py                ZaloMessenger (Messenger impl trên bridge)
│
├── controllers/
│   └── message_router.py    Single inbound boundary (tenant gate, route to agent)
│
├── repositories/            Tầng truy cập DB (BossRepo, TaskRepo, …)
├── services/                Domain services (tasks, people, reminders, lark sync, …)
├── infrastructure/          External clients (lark, openai, cohere, qdrant, observability, crypto)
└── utils/                   Helpers (text, dates, validation)
```

**Inbound flow:** `Channel → IncomingMessage (UUIDs đã resolve) → MessageRouter → secretary_agent → tools → reply`.

**Outbound (legacy):** Code cũ gọi `telegram.send(chat_id, text)` — shim tự dispatch về Zalo nếu conversation thuộc provider zalo.

---

## Roadmap

**Phase 6b — Zalo hardening (kế tiếp demo):**
- Multi-account: 1 process / Zalo account, table `zalo_account`, encrypted session (Fernet)
- Rate limiter (per-thread + per-min/account + daily cap, jitter)
- Circuit breaker + daily session refresh cron
- QR re-login CLI, fatal disconnect → Telegram alert
- Spec: `docs/superpowers/specs/2026-04-30-phase-6b-zalo-channel-design.md`

**Phase 6c+ — kênh khác:**
- Messenger (unofficial / Cloud API)
- WhatsApp Cloud API
- Web chat (FastAPI WebSocket)
- Zalo OA (separate provider, OAuth + webhook)

**Phase 7 — Admin UI:** Web UI quản lý workspace + Zalo accounts (thay CLI cho self-host SaaS).

**Continuous:**
- Voice STT (Whisper) trên file đính kèm
- Audit log redaction + export
- Per-boss LLM credentials (Phase 3 khung đã có)

---

## Bảo mật

- Mỗi workspace tách biệt; member/partner chỉ thao tác task của mình.
- Session Zalo lưu plaintext ở demo — Phase 6b sẽ encrypt (Fernet).
- Reset workspace 2-step confirm.
- SQL injection chặn bằng whitelist cột trong dynamic UPDATE.
