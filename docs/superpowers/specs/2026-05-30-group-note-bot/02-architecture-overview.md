[← Index](./README.md)

# §2. Tổng quan kiến trúc

## 2.1 Phân lớp

```
┌─────────────────────────────────────────────────────────────────┐
│              Channels (inbound + outbound)                      │
│  ┌──────────────────────┐                                       │
│  │  Zalo (personal)     │  Telegram / Messenger / WhatsApp      │
│  │  zlapi-py legacy     │  (module-ready, defer Phase 1+)       │
│  │  dual-mode bot acc:  │                                       │
│  │   • platform pool    │                                       │
│  │   • boss-owned       │                                       │
│  └────┬─────────────────┘                                       │
└───────┼─────────────────────────────────────────────────────────┘
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Channel Router                            │
│   Chuẩn hoá event inbound → InboundMessage                     │
│   Resolve boss_id qua bảng account_links                       │
│   Resolve bot_account_id (acc nào nhận → acc nào reply)        │
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

### 2.1.1 Channel capability matrix

Mỗi channel adapter cài interface `ChannelAdapter` trong [§10.2](./10-tech-stack-infra.md#102-project-structure-đề-xuất).
Capability flag để code core không cần biết platform. MVP **chỉ Zalo**;
các provider khác ở đây là reference cho Phase 1+:

| Capability | Zalo personal (MVP) | Telegram (P1) | Messenger (P1+) | WhatsApp Cloud (P1+) |
|---|---|---|---|---|
| `inbound.has_webhook` | ❌ (poll/long-poll) | ✓ | ✓ | ✓ |
| `inbound.supports_groups` | ✓ | ✓ | partial | group cloud beta |
| `inbound.supports_mentions` | ✓ (manual parse) | ✓ | ✓ | ✓ |
| `inbound.media_kinds` | text, image, file, voice, sticker, url | text, image, file, voice, sticker | text, image, file | text, image, file |
| `outbound.send_text` | ✓ | ✓ | ✓ | ✓ |
| `outbound.reply_to_msg` | ✓ | ✓ | ✓ | ✓ |
| `outbound.send_file` | ✓ | ✓ | ✓ | ✓ |
| `outbound.typing_indicator` | ✓ (legacy có) | ✓ | ✓ | ❌ |
| `member.list_api` | partial (legacy code parse) | ✓ | limited | limited |
| `auth.kind` | personal cookies (dual-mode: platform/boss-owned) | bot token (platform) | page token | system user |
| `requires_admin_role_for_core` | ❌ (degraded: pin in-chat, force kick member không dùng được) | ❌ | ❌ | ❌ |

**Nguyên tắc**: bot vận hành ở chế độ **member thường** trong group là
default. Các tool cần admin (vd `pin_in_chat`, `kick_member` Phase 1+)
phải declare `requires_admin=True`; engine kiểm tra capability + role
hiện tại của bot acc → degrade gracefully (giải thích sếp "em chưa
được admin nên không pin được trong chat, nhưng pin nội bộ vào note
được anh nhé"). KHÔNG block core features (capture, note, Q&A,
reminder) khi bot không phải admin.

Adapter mới = drop file vào `src/channels/<name>.py` + đăng ký vào `channels/__init__.py`. Core không cần sửa.

## 2.2 Luồng data — happy paths

**Capture thụ động** (mỗi inbound message):

```
Channel webhook / poll
   ▼
Channel adapter chuẩn hoá → InboundMessage (carries bot_account_id)
   ▼
Router lookup account_links → boss_id   (không có → drop)
   ▼
Verify bot_account_assignments(boss_id, provider) == this bot_account_id
   │   (mismatch → drop, log warn — 1 sếp chỉ thuộc 1 bot acc/provider)
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
│   /api/oauth/google/callback                    │
│   /api/oauth/plugin/<name>/callback             │
│   /api/public/v1/*  (read-only MVP)             │
│   /admin/*  (role-gated)                        │
│   /app/*   (user pages)                         │
│                                                 │
│ Background tasks (asyncio):                     │
│   - Zalo poll workers (1 task / bot_account)    │
│   - NoteUpdater queue worker                    │
│   - Reminder scheduler (§13)                    │
│   - EventBus dispatcher (§14 — internal subs)   │
│   - Bot account health check                    │
│   - Subscription expiry checker (hàng ngày)     │
│   - (Phase 1) digest scheduler                  │
│   - (Phase 1) Telegram webhook router           │
└─────────────────────────────────────────────────┘
       │
       ├─ Postgres  (asyncpg)
       ├─ Qdrant    (HTTP)
       └─ External LLM APIs
```

1 process = deploy đơn giản. Khi scale yêu cầu, NoteUpdater nâng thành
worker process riêng dễ dàng (input của nó là message events).

## 2.5 Đã chốt

- Single-process MVP. Split web/worker hoãn tới khi LLM call saturate request handling (~50 sếp).
- Bot account pool — platform sở hữu, mỗi (boss × provider) gắn cứng 1 acc. Chi tiết [§3.8](./03-identity-channel-linking.md#38-mô-hình-bot-account--dual-mode).
- Channel adapter có capability matrix (§2.1.1) → core không phụ thuộc provider.
