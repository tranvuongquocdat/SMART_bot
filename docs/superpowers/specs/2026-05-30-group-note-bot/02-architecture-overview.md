[← Index](./README.md)

# §2. Tổng quan kiến trúc

## 2.1 Phân lớp

```
┌─────────────────────────────────────────────────────────────────┐
│              Channels (inbound + outbound)                      │
│  ┌──────────┐  ┌─────────────┐  ┌──────────────────┐            │
│  │  Zalo    │  │  Telegram   │  │  Lark Messenger  │ (hoãn)     │
│  │  OA SDK  │  │  Bot SDK    │  │  (Phase 1)       │            │
│  └────┬─────┘  └──────┬──────┘  └────────┬─────────┘            │
└───────┼───────────────┼──────────────────┼──────────────────────┘
        ▼               ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Channel Router                            │
│   Chuẩn hoá event inbound → InboundMessage                     │
│   Resolve boss_id qua bảng account_links                       │
│   Drop nếu không có sếp linked nào trong chat                  │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Capture & Indexing                          │
│   • bảng messages (PostgreSQL)                                 │
│   • FTS tsvector index (unaccent + simple)                     │
│   • Qdrant vector store (semantic) — upsert async              │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Agent Layer (§6)                          │
│                                                                 │
│   Operations:                                                   │
│     - GroupNoteUpdater  (debounce/threshold)                   │
│     - InGroupResponder  (@bot mention)                          │
│     - DMResponder       (sếp DM)                                │
│                                                                 │
│   Tools:                                                        │
│     - core: search_history, refresh_note, edit_note, ...       │
│     - plugin: load động per-boss                                │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                       LLM Abstraction (§7)                      │
│                                                                 │
│   Provider clients (1 file/cái):                                │
│     - OpenAICompatibleClient (OpenAI, Groq, OpenRouter, …)     │
│     - AnthropicClient                                          │
│     - GeminiClient                                             │
│                                                                 │
│   ModelRegistry: tên model → capabilities, cost, tier          │
│   Router: pick(boss_config, op_type) → (provider, model)       │
└─────────────────────────────────────────────────────────────────┘

  Side surfaces
  ─────────────

┌─────────────────────────────────────────────────────────────────┐
│                       Web Application (§9)                      │
│                                                                 │
│   - User pages: Dashboard, Groups, Notes, Channels, ...        │
│   - Superadmin pages: Bosses, Payments, Revenue                │
│   - OAuth callback (Google login, plugin OAuth)                │
│   - Channel linking endpoint (deep-link tokens)                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                       Scheduler                                 │
│                                                                 │
│   - Flush note debounce                                        │
│   - Check subscription hết hạn                                 │
│   - (Phase 1) Gửi daily digest                                 │
│   - (Phase 1) Stalled-work alerts                              │
└─────────────────────────────────────────────────────────────────┘
```

## 2.2 Luồng data — happy paths

**Capture thụ động** (mỗi inbound message):

```
Channel webhook
   ▼
Channel adapter chuẩn hoá
   ▼
Router lookup account_links → boss_id   (không có → drop)
   ▼
messages INSERT  (Postgres + FTS index + Qdrant upsert async)
   ▼
NoteUpdater.schedule(boss_id, chat_id)   (debounce 10 phút, threshold 30 msg)
   ▼
LLM (smart tier) rebuild markdown của group_note
   ▼
group_notes UPDATE + group_note_versions INSERT
```

**Op on-demand** (`@bot` trong group):

```
Tagged message → router → boss_id resolved
   ▼
Agent.handle(InGroupResponder)
   ▼     tools = core + plugins đã bật cho boss
         context = group_note hiện tại + messages gần đây (giới hạn)
LLM (smart cho reasoning, fast cho ack ngắn)
   ▼
Outbound: reply trong cùng group
   ▼
outbound_messages INSERT
```

## 2.3 Multi-tenant

- Multi-tenant từ ngày 1. 1 server process, N sếp.
- Mọi bảng domain có cột `boss_id`. Mọi query filter theo `boss_id` ở
  tầng repository. Không dùng PG row-level-security (kept simple,
  enforce ở code).
- Object cross-boss: `users` (chứa cả superadmin), config platform-wide
  (LLM defaults, plugin manifests).

## 2.4 Topology vận hành

```
┌─────────────────────────────────────────────────┐
│ 1 FastAPI app (1 Python process)                │
│                                                 │
│ Routers:                                        │
│   /api/channels/zalo/webhook                    │
│   /api/channels/telegram/webhook                │
│   /api/oauth/google/callback                    │
│   /api/oauth/plugin/<name>/callback             │
│   /admin/*  (role-gated)                        │
│   /app/*   (user pages)                         │
│                                                 │
│ Background tasks (asyncio):                     │
│   - NoteUpdater queue worker                    │
│   - Subscription expiry checker (hàng ngày)     │
│   - (Phase 1) digest scheduler                  │
└─────────────────────────────────────────────────┘
       │
       ├─ Postgres  (asyncpg)
       ├─ Qdrant    (HTTP)
       └─ External LLM APIs
```

1 process = deploy đơn giản. Khi scale yêu cầu, NoteUpdater nâng thành
worker process riêng dễ dàng (input của nó là message events).

## 2.5 Mở

- **(mở) Single-process vs split web/worker** — single OK cho ~50 sếp
  đầu. Split hoãn tới khi LLM call saturate request handling.
