# Group Note Bot — Thiết kế chi tiết (Bản thảo v1, Đợt 1)

**Trạng thái:** Bản thảo · Đợt 1/2 (Sản phẩm · Kiến trúc · Định danh · Group Note · Capture)
**Ngày tạo:** 2026-05-30
**Branch:** `main` (rebuild, đã collapse)
**Tham chiếu code cũ:** `git show archive/legacy:<path>`

## Cách đọc tài liệu

Đây là nửa đầu của spec. Đợt 2 sẽ cover: Agent layer, LLM abstraction, Plugin
architecture, Web admin, Tech stack, và tổng hợp open questions.

**Cách lặp review:**
- Anh đọc từng section, reply theo section.
- Cú pháp: `section X: <thay đổi>` · `section X expand` · `section X looks good` · `Đợt 1 OK`.
- Section gắn nhãn **(mở)** = decision chưa chốt, em đã surface tại chỗ.
- Khi Đợt 1 OK → em viết Đợt 2. Khi cả spec OK → em invoke `writing-plans`
  để generate implementation plan.

## Mục lục

1. Tầm nhìn sản phẩm & phạm vi
2. Tổng quan kiến trúc
3. Định danh & Kết nối kênh
4. Group Note (hiện vật cốt lõi)
5. Capture flow & Data model

Section 6–11 ở Đợt 2.

---

## 1. Tầm nhìn sản phẩm & phạm vi

### 1.1 Vấn đề

Sếp SME Việt Nam sống trong chat — Zalo là chính, Telegram phụ. Họ quản nhiều
group chat (sale, marketing, tech, đối tác). Họ:

- Sót quyết định bị chôn trong thread dài.
- Quên đã chốt gì tuần trước.
- Không biết các task đang mở rải rác ở các nhóm.
- Khó tra "ai nói gì về X" cách đây vài tuần.
- Mất buổi sáng để scroll.

Tool có sẵn (Asana, Notion, Slack AI, Otter) không phù hợp: bắt rời Zalo,
target user English-first/desktop-first, hoặc quá generic / nặng.

### 1.2 Đối tượng

**Persona chính** — sếp SME / leader team Việt Nam:

- Dùng Zalo cho >80% giao tiếp công việc
- Quản 3–15 group chat
- Có 5–50 nhân viên / đối tác
- Không phải dân tech (không tự paste API key vào setting nếu thiếu UI)
- Trả VND, thích chuyển khoản hơn thẻ

**Persona phụ** — nhân viên của sếp. Tương tác với bot **chỉ** trong group
mà sếp có mặt. Không DM bot, không có cấu hình riêng. Cách này né hoàn
toàn bài toán identity-resolution.

### 1.3 Trục sản phẩm — "group note"

Hiện vật chính của bot là **1 trang document sống cho mỗi group chat**.
Mỗi group có DUY NHẤT 1 markdown note, tự update từ cuộc trò chuyện,
sếp edit được, và là nguồn sự thật cho mọi operation khác:

- Tóm tắt → re-emit note
- Q&A → search note + lịch sử raw
- Action items → view trích từ section "Việc đang mở" của note
- Digest cross-group (hoãn) → roll-up note của tất cả group của sếp

Cách design này gom nhiều feature về 1 hiện vật bền vững, UX rõ ràng:
**1 group = 1 note luôn được cập nhật**.

### 1.4 Phạm vi MVP (Phase 0)

| Layer | Khả năng |
|---|---|
| **Capture** | Mọi message trong group nào có sếp linked. Lưu text raw + tên hiển thị người gửi. |
| **Group note** | 1 note markdown/group, 7 section (§4.2). Auto-update theo debounce + threshold. Sếp edit được trên web. |
| **Op in-group** | `@bot tóm tắt` / `@bot refresh note` · `@bot Q&A` trên note + history · auto-detect action item nhúng vào note |
| **DM với sếp** | Q&A cross-group · "tóm tắt group X tuần này" · list việc đang mở · KHÔNG có push tự động |
| **Web (user)** | Sidebar 8 section (Dashboard, Groups, Action Items, Digests-disabled, Channels, Plugins, Usage, Settings). Đợt 2 §9. |
| **Web (super)** | 3 page — Bosses, Payments, Revenue. Role-gated qua env var. |
| **Channel** | Zalo (ưu tiên) + Telegram. Lark Messenger hoãn. |
| **AI** | Provider abstraction (OpenAI / Groq / Anthropic / Gemini / Custom). 2-tier fast/smart. BYO key. |
| **Plugin** | Kiến trúc sẵn sàng; **0 plugin ship**. |
| **DB** | PostgreSQL + Qdrant. |
| **Auth (user)** | Google OAuth + email/password (fallback). |
| **Auth (channel)** | Deep-link qua DM `/start <token>`. |
| **Subscription** | Manual: hiện VietQR + superadmin click "đã thanh toán". |

### 1.5 Hoãn (Phase 1+)

- Daily digest DM (toggle + lịch)
- Stalled-work alerts
- **Media ingest ngoài text** — decision ở §1.7 + §5.4
- Plugin ship: Google Calendar, Lark Base
- Lark Messenger channel
- Auto-detect thanh toán (Casso/SePay webhook)
- People insights, mood analytics
- Đa tiền tệ, subscription quốc tế

### 1.6 KHÔNG làm

- Không build billing engine. Sếp chuyển khoản; em click "đã thanh toán"
  trong admin. Không Stripe, không auto-invoice.
- Không build cross-channel identity resolution. "Anh Tân" để nguyên text
  như hiển thị — không map về `user_id`.
- Không DM nhân viên. Bot chỉ DM sếp đã linked.
- Không offer self-hosted single-tenant. Multi-tenant từ ngày 1.

### 1.7 Mở

- **(mở) Media ingest trong MVP** — xem §5.4, so sánh A / B / C.
  Em recommend **B** (URL fetch + voice transcribe).

---

## 2. Tổng quan kiến trúc

### 2.1 Phân lớp

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
│                       Agent Layer                               │
│   (Đợt 2 §6)                                                    │
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
│                       LLM Abstraction                           │
│   (Đợt 2 §7)                                                    │
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
│                       Web Application                           │
│   (Đợt 2 §9)                                                    │
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

### 2.2 Luồng data — happy paths

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

### 2.3 Multi-tenant

- Multi-tenant từ ngày 1. 1 server process, N sếp.
- Mọi bảng domain có cột `boss_id`. Mọi query filter theo `boss_id` ở
  tầng repository. Không dùng PG row-level-security (kept simple,
  enforce ở code).
- Object cross-boss: `users` (chứa cả superadmin), config platform-wide
  (LLM defaults, plugin manifests).

### 2.4 Topology vận hành

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

### 2.5 Mở

- **(mở) Single-process vs split web/worker** — single OK cho ~50 sếp
  đầu. Split hoãn tới khi LLM call saturate request handling.

---

## 3. Định danh & Kết nối kênh

### 3.1 Tài khoản web (boss → users)

- Sếp đăng ký qua Google OAuth (chính) hoặc email/password (fallback).
- 1 row `users` per sếp. Cột: id, email, name, google_sub,
  password_hash (nullable), role, subscription_status, subscription_plan,
  subscription_expiry.
- `role ∈ {boss, superadmin}`. Auto-set superadmin khi email khớp env
  `SUPERADMIN_EMAILS` lúc login.

### 3.2 Linking kênh qua deep-link

Bot do platform sở hữu (1 Zalo OA, 1 Telegram bot, 1 Lark app). Mỗi sếp
link identity kênh qua DM-deep-link:

```
Web (sếp đã login):
  Click [Kết nối Zalo] ở page /channels
     │
     ▼  server generate token (16 url-safe bytes), TTL 10 phút
     │  lưu vào linking_tokens
     │
     ▼  redirect tới deep-link:
        https://zalo.me/<OA_ID>?param=<token>            (Zalo)
        https://t.me/<BOT_USERNAME>?start=<token>        (Telegram)

Điện thoại sếp:
  Zalo/Telegram mở chat với bot.
  Pre-populate "/start <token>" — sếp tap Gửi.
     │
     ▼  bot nhận DM
     │  parse token từ payload
     │  lookup linking_tokens → boss_id
     │  INSERT account_links (boss_id, provider, provider_user_id, linked_at)
     │  DELETE token row
     │  reply "✓ Đã kết nối Zalo. Em là bot của anh ở đây."

Web (auto-refresh):
  Page channels hiện: Zalo ✓ Connected
```

### 3.3 Schema

```sql
account_links (
  boss_id          INTEGER NOT NULL REFERENCES users(id),
  provider         TEXT    NOT NULL,                  -- 'zalo' | 'telegram' | 'lark_msg'
  provider_user_id TEXT    NOT NULL,
  linked_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (provider, provider_user_id)
);
CREATE INDEX idx_account_links_boss ON account_links(boss_id);

linking_tokens (
  token       TEXT PRIMARY KEY,
  boss_id     INTEGER NOT NULL REFERENCES users(id),
  provider    TEXT NOT NULL,
  expires_at  TIMESTAMPTZ NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_linking_tokens_expires ON linking_tokens(expires_at);
```

### 3.4 Phát hiện thành viên nhóm

Khi message đến từ 1 group chat:

```python
# Pseudo
async def resolve_group_owner(chat_id, provider):
    member_ids = await channel.list_members(chat_id)
    if not member_ids:
        # Fallback nếu channel API hạn chế đọc membership:
        member_ids = await message_repo.distinct_senders(chat_id, days=30)
    rows = await db.fetch(
        "SELECT boss_id FROM account_links "
        "WHERE provider = $1 AND provider_user_id = ANY($2)",
        provider, member_ids,
    )
    return [r["boss_id"] for r in rows]
```

Không có sếp linked nào trong chat → bot drop event im lặng (không reply,
không capture).

### 3.5 Nhiều sếp cùng nhóm (edge case)

Nếu 2 sếp đã linked cùng nằm trong 1 group, cả 2 đều nên thấy group
trong dashboard của mình.

- `group_notes` key theo `(boss_id, provider, chat_id)` — cùng 1 group
  render thành 2 note (1/sếp), edit độc lập.
- Bot reply trong group 1 lần. Attribution: sếp nào tag `@bot` là sếp
  đó; nếu tag trống, lấy sếp link sớm nhất.

### 3.6 Mở

- **(mở) UX nhiều sếp: tách vs gộp.** Tách đơn giản hơn (mỗi sếp
  experience độc lập). List vào Đợt 2.

---

## 4. Group Note (hiện vật cốt lõi)

### 4.1 Tại sao 1 note/group

Không có hiện vật bền vững → mỗi lần Q&A đều start từ message raw →
context tốn, câu trả lời không nhất quán. Có rolling note thì:

- Lịch sử quyết định được bảo tồn (không bị mất trong scroll-back).
- Action item có nơi sống duy nhất.
- Context của LLM Q&A giảm từ ~50k token raw chat xuống ~1k token note
  + retrieval.
- Sếp có UI đọc "tình trạng group" trong 1 màn hình.

### 4.2 Schema 7 section

Section không có content thì ẩn khi render. Header do code template;
LLM fill content.

```markdown
# {group_name}
Cập nhật lần cuối: {iso_timestamp} · {msg_count_7d}/ngày · trạng thái: {emoji}

## ⚡ Cần sếp xử lý          (ẩn nếu trống)
- bullet ngắn, việc rõ ràng đang cần sếp action

## 📌 Đang focus              (max 3–5 bullet)
- group đang đẩy chuyện gì hiện tại

## ✅ Việc đang mở            (task list — chủ + hạn)
- [ ] {person} — {task} · {hạn_hoặc_open}
- ⚠ {person} — {task} · QUÁ HẠN {Nd}

## 🚧 Đang tắc / Rủi ro      (ẩn nếu trống)
- blocker, việc tắc, risk

## 📜 Đã quyết                (log quyết định, append-only)
- {quyết định} ({attributed_to}, {date})

## 💬 Câu hỏi treo            (ẩn nếu trống)
- câu hỏi mở, visible cho team

## 👥 Người active (7d)
- {name} ({count}) · ...

## 📦 Lưu trữ
- [{period}](archive link)
```

**Nguyên tắc design:**
- Exception đặt trước (⚡, 🚧). Sếp scan top thấy ngay.
- Giá trị bền vững ở dưới. `📜 Đã quyết` là log append-only.
- LLM **không bao giờ** xoá entry trong `📜 Đã quyết`. Chỉ manual edit
  xoá được.
- `👥 Người active` tính từ count message, không phải LLM suy ra.

### 4.3 Vòng đời update

3 trigger (bất kỳ cái nào queue update):

| Trigger | Khi nào | Lý do |
|---|---|---|
| **Debounce 10 phút** | Group có message trong X phút trước; X phút trôi kể từ message mới nhất | Cuộc trò chuyện đã lắng |
| **Threshold 30 msg** | 30 message mới kể từ lần update note gần nhất | Đừng đợi quá lâu cho group đông |
| **On-demand** | `@bot refresh note` trong group, hoặc nút "Refresh" trên web | User chủ động |

Quy trình update:

```
1. Acquire lock (boss_id, chat_id)   (asyncio.Lock cho MVP)
2. Load group_note.content hiện tại
3. Load message mới từ group_note.last_seen_message_id
4. Build LLM prompt:
   - System: "Update group note. Giữ nguyên section X, Y (đã edit thủ
              công). Chỉ update D, E, F, G. Section '📜 Đã quyết' chỉ
              append, không xoá."
   - Input: note hiện tại + delta messages
5. LLM (smart tier) emit markdown mới
6. Validate: đủ 7 header (renderer ẩn cái rỗng)
7. UPDATE group_notes SET content, last_seen_message_id, updated_at
   INSERT group_note_versions cho history
8. Release lock
```

### 4.4 Edit thủ công & merge conflict

Web UI hiện note trong markdown editor. Sếp click "Edit", save.

Để lần update tự động sau không ghi đè edit thủ công:

- Khi save, record `manually_edited_sections` (set tên header có content
  khác với version cuối LLM emit).
- Lần auto-update sau, LLM được instruct: "Section {A, B, C} đã edit
  thủ công, giữ nguyên. Chỉ update {D, E, F, G}."
- Granularity = per-section, không per-line. Toggle `Cho bot quản section
  này lại` clear flag cho section đó.

`group_notes.manually_edited_sections` là JSONB array tên section.

### 4.5 Versioning & lưu trữ

- Mỗi lần update INSERT 1 row vào `group_note_versions`. ~vài kB/cái.
- Web hiện timeline version + diff view.
- Sau 30 ngày, version cũ compact: giữ 50 cái gần nhất + monthly snapshot.

### 4.6 Schema DB

```sql
group_notes (
  id                         BIGSERIAL PRIMARY KEY,
  boss_id                    INTEGER NOT NULL REFERENCES users(id),
  provider                   TEXT NOT NULL,
  chat_id                    TEXT NOT NULL,
  group_name                 TEXT,
  content                    TEXT NOT NULL DEFAULT '',
  manually_edited_sections   JSONB NOT NULL DEFAULT '[]'::jsonb,
  last_seen_message_id       BIGINT,
  status                     TEXT NOT NULL DEFAULT 'active',  -- active | quiet | stalled
  msg_count_7d               INTEGER NOT NULL DEFAULT 0,
  updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (boss_id, provider, chat_id)
);
CREATE INDEX idx_group_notes_boss ON group_notes(boss_id);

group_note_versions (
  id            BIGSERIAL PRIMARY KEY,
  group_note_id BIGINT NOT NULL REFERENCES group_notes(id) ON DELETE CASCADE,
  content       TEXT NOT NULL,
  emitted_by    TEXT NOT NULL,  -- 'llm' | 'user'
  emitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_group_note_versions_note ON group_note_versions(group_note_id, emitted_at DESC);
```

### 4.7 Mở

- **(mở) Schema 7 section cố định vs cấu hình được per-boss.** Cố định
  cho MVP. Cấu hình được = thêm param vào prompt template. List Đợt 2.

---

## 5. Capture flow & Data model

### 5.1 Pipeline nhận message

```
Channel webhook
   ▼
Channel adapter parse event platform → InboundMessage
   ▼
Router resolve boss_id qua account_links
   │   không có linked boss → drop im lặng
   ▼
Persist:
  1. INSERT INTO messages
  2. tsvector auto-build (Postgres TRIGGER)
  3. EMBED + UPSERT Qdrant   (async, không block webhook ack)
   ▼
Schedule NoteUpdater cho (boss_id, chat_id)
   ▼
Return 200 OK cho channel webhook
```

Embedding async vì tốn 100–500ms, không nên block webhook ack (channel
retry khi response chậm).

### 5.2 Schema `messages`

```sql
messages (
  id                 BIGSERIAL PRIMARY KEY,
  boss_id            INTEGER NOT NULL REFERENCES users(id),
  provider           TEXT NOT NULL,
  chat_id            TEXT NOT NULL,
  chat_type          TEXT NOT NULL,        -- 'group' | 'dm'

  provider_msg_id    TEXT,                 -- msg id của platform, để dedup
  reply_to_msg_id    BIGINT REFERENCES messages(id),

  sender_provider_id TEXT,                 -- user id của platform
  sender_name        TEXT,                 -- tên hiển thị (KHÔNG resolve!)

  text               TEXT,                 -- body raw
  media_kind         TEXT,                 -- NULL | 'voice' | 'image' | 'file' | 'sticker' | 'url'
  media_url          TEXT,                 -- nơi fetch
  media_text         TEXT,                 -- text trích (transcript, OCR, fetched body)

  ts                 TIMESTAMPTZ NOT NULL, -- timestamp của platform
  ingested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  fts                tsvector,             -- update qua trigger

  UNIQUE (provider, chat_id, provider_msg_id)
);
CREATE INDEX idx_messages_chat ON messages(boss_id, provider, chat_id, ts DESC);
CREATE INDEX idx_messages_fts ON messages USING GIN(fts);
```

**Lưu ý:**
- `media_text` là text equivalent để search. Voice → transcript. URL →
  body bài báo fetched. Image → OCR (Phase 1). FTS index cả `text` và
  `media_text`.
- `sender_name` là tên hiển thị **tại lúc capture**. Không lookup,
  không normalise. Đây là lựa chọn "không identity resolution" rõ ràng.
- Dedup qua `UNIQUE(provider, chat_id, provider_msg_id)` để channel retry
  idempotent.

### 5.3 Indexing: FTS + Qdrant

**Postgres FTS:**
- Dùng cho keyword lookup ("có ai nói X không").
- Tiếng Việt: config `simple` + extension `unaccent` + `pg_trgm` để
  match không phân biệt dấu.
- Index trên `text` và `media_text`.

**Qdrant:**
- **1 collection duy nhất**, filter qua payload `boss_id`. Tránh
  overhead quản N collection. Boss-filter chạy nhanh.
- Embedding: `text-embedding-3-small` (1536 dims) cho MVP. Switch được
  qua LLM-abstraction ở Đợt 2.
- Granularity: **per-message** cho MVP. Message Zalo phần lớn ngắn.
  Paragraph chunking hoãn.
- Payload: `{boss_id, provider, chat_id, ts, sender_name}` để filterable.

**Hybrid retrieval (Q&A):**
```
1. FTS pre-filter (boss_id, chat_id?, optional date range) → ≤500 candidate
2. Vector rank top-20 trong đó (Qdrant với payload filter)
3. Pass cho LLM cùng group_note hiện tại
```

### 5.4 Xử lý media — decision mở

| Option | MVP có gì | Effort | Risk nếu skip |
|---|---|---|---|
| **A. Chỉ text** | Voice / image / file / URL lưu `media_kind` + `media_url`; `media_text` rỗng. Note bỏ qua. | 0 | Note miss ~30–50% content của group Zalo SME điển hình. |
| **B. URL fetch + voice transcribe** | `media_text` populate cho URL (body fetched) và voice (Whisper-style transcribe). Note cover content của chúng. | +2 tuần | Image OCR + file extract vẫn thiếu — gap nhỏ hơn. |
| **C. Full media ingest** | A + B + OCR ảnh + extract PDF/docx. | +4 tuần | Ship chậm. |

Recommendation: **B**. Group Zalo voice-heavy → cost xứng đáng. Image /
file để Phase 1.

### 5.5 Lưu trữ & quyền riêng tư

**Policy MVP:**
- `messages`: giữ vô thời hạn khi subscription còn active.
- Subscription hết hạn: bot stop capture (channel webhook drop). Data hiện
  có giữ 90 ngày; sau đó web hiện prompt "delete hoặc export"; default
  sau 30 ngày kể từ prompt là delete.
- `group_note_versions` cũ hơn 30 ngày → compact: 50 cái gần nhất +
  monthly snapshot.
- Không share dataset analytics off-platform. Không telemetry content
  cho bên thứ 3.

**Export data per-boss (Phase 1):** Nút "Tải dữ liệu của tôi" trên web →
ZIP chứa messages + notes dạng markdown. Feature tạo trust.

### 5.6 Log message gửi đi

```sql
outbound_messages (
  id                  BIGSERIAL PRIMARY KEY,
  boss_id             INTEGER NOT NULL REFERENCES users(id),
  provider            TEXT NOT NULL,
  chat_id             TEXT NOT NULL,
  reply_to_message_id BIGINT REFERENCES messages(id),
  content             TEXT NOT NULL,
  trigger             TEXT NOT NULL,        -- 'mention' | 'dm' | 'scheduled' | 'system'
  sent_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status              TEXT NOT NULL,        -- 'sent' | 'failed'
  error               TEXT
);
```

Dùng cho: debug, observability, audit ("bot có thật sự reply không?"),
và build digest tương lai.

### 5.7 Mở

- **(mở) Voice transcription** — API (OpenAI/Groq Whisper) vs tự host
  (whisper.cpp). API cho MVP; tự host Phase 2 nếu cost quan trọng.
- **(mở) Image OCR** — hoãn Phase 1.
- **(mở) Quyền "xoá tôi khỏi data" cho cá nhân được mention** — hoãn.

---

## Đợt 2 preview

Sau khi Đợt 1 OK:

- §6 Agent layer — operation routing, tool calling chain, **multi-agent
  hay không**, quản context window
- §7 LLM abstraction — provider clients, ModelRegistry, 2-tier routing,
  fallback khi gap capability
- §8 Plugin architecture — manifest format, OAuth flow, settings
  auto-render
- §9 Web admin — user pages + superadmin pages, auth, channel wizard
- §10 Tech stack & infra — PG + Qdrant + FastAPI + HTMX, Docker, env,
  observability
- §11 Tổng hợp open questions
