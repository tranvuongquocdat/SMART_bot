# Group Note Bot — Thiết kế chi tiết (Bản thảo v1)

**Trạng thái:** Bản thảo · Full v1 (Đợt 1 + Đợt 2)
**Ngày tạo:** 2026-05-30
**Branch:** `main` (rebuild, đã collapse)
**Tham chiếu code cũ:** `git show archive/legacy:<path>`

## Cách đọc tài liệu

Đây là spec đầy đủ Bản thảo v1, gồm 11 section. Anh đọc, anh note, rồi
mình trao đổi 1 lượt cuối.

**Cách lặp review:**
- Đọc qua một lượt. Có gì note vào.
- Reply gọn theo section: `section X: <thay đổi>` · `section X expand` ·
  `section X looks good` · hoặc một message gom các điểm.
- Open questions tổng hợp ở §11; close bằng cú pháp ngắn (ví dụ
  `media ingest: B`).
- Khi tất cả OK → em invoke `writing-plans` tạo implementation plan.

## Mục lục

1. Tầm nhìn sản phẩm & phạm vi
2. Tổng quan kiến trúc
3. Định danh & Kết nối kênh
4. Group Note (hiện vật cốt lõi)
5. Capture flow & Data model
6. Agent layer
7. LLM abstraction
8. Plugin architecture
9. Web admin
10. Tech stack & infrastructure
11. Tổng hợp open questions

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
| **Web (user)** | Sidebar 8 section (Dashboard, Groups, Action Items, Digests-disabled, Channels, Plugins, Usage, Settings). §9. |
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
  experience độc lập). Em recommend tách.

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

- **(mở) Schema 7 section cố định vs cấu hình được per-boss.** Em
  recommend cố định cho MVP.

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
  qua LLM-abstraction ở §7.
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
  (whisper.cpp). Em recommend API cho MVP.
- **(mở) Image OCR** — hoãn Phase 1.
- **(mở) Quyền "xoá tôi khỏi data" cho cá nhân được mention** — hoãn.

---

## 6. Agent layer

### 6.1 Operations & routing

3 loại operation:

| Operation | Trigger | Mục tiêu | Output |
|---|---|---|---|
| **GroupNoteUpdater** | Debounce/threshold (§4.3) | Rebuild markdown của group_note | UPDATE group_notes |
| **InGroupResponder** | `@bot` mention trong group | Trả lời tại group | Outbound message |
| **DMResponder** | Sếp DM cho bot | Trả lời sếp riêng | Outbound DM |

Router quyết định op từ inbound event:
- DM từ linked boss → DMResponder
- Group msg có `@bot` mention → InGroupResponder
- Mọi group msg khác → chỉ trigger NoteUpdater (no reply)

### 6.2 Single agent vs multi-agent

Đây là câu hỏi anh đặt rõ. Em phân tích:

**Multi-agent (kiểu LangGraph)**: 1 op = nhiều LLM call cho nhiều
"agent" specialised (vd ResearcherAgent → SearcherAgent → WriterAgent).
Pro: phân vai bài bản. Con: latency tăng 3–10x, debug khó, prompt phình.

**Single agent per op**: mỗi op = 1 LLM call có tool. Tool dispatcher chạy
tool, LLM tiếp tục. Simple, debug dễ, latency thấp.

Em recommend **single agent per op** vì:
- Op của mình không phức tạp đến mức cần phân vai (NoteUpdater = "rebuild
  markdown từ input"; Responder = "trả lời câu hỏi với tool")
- Multi-agent thường wins khi task có planning phức tạp nhiều bước —
  ở đây không có.
- Cost & latency là constraint thực tế.

Nhưng giữa các op vẫn "đa agent" theo nghĩa **3 op = 3
prompt/persona/model tier khác nhau**:
- **NoteUpdater**: prompt "biên tập markdown", smart model, tool tối
  thiểu (chỉ `edit_note`)
- **InGroupResponder**: prompt "thư ký trong group", smart hoặc fast tuỳ
  message, full core tool + plugin tool
- **DMResponder**: prompt "thư ký riêng cho sếp", smart, full tool

**Quyết định:** single-agent per op, 3 op tách biệt. Multi-agent giữ
làm option Phase 2 nếu trải nghiệm thật cho thấy task quá phức tạp.

### 6.3 Tool calling

Follow chuẩn OpenAI function calling. Tool đăng ký vào dispatcher:

```python
@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict             # JSON Schema
    handler: Callable[[dict, BossContext], Awaitable[ToolResult]]
```

**Core tools (always available):**

| Tool | Mô tả |
|---|---|
| `search_history(query, group?, days?)` | Hybrid FTS + vector retrieval trên messages |
| `read_group_note(group_id)` | Trả về note hiện tại |
| `refresh_group_note(group_id)` | Trigger NoteUpdater on-demand |
| `edit_group_note(group_id, section, new_content)` | Sửa 1 section (bot dùng cho DMResponder) |
| `list_action_items(group_id?, status?)` | List task từ section "Việc đang mở" |
| `mark_action_item(item_id, status)` | Đánh dấu done/cancel |
| `list_groups()` | Liệt kê group sếp đang link |
| `current_time()` | Thời gian hiện tại theo TZ sếp |

**Plugin tools** (load động per-boss, §8).

**Tool calling loop:**

```python
async def agent_loop(op_ctx, max_depth=5):
    messages = build_initial(op_ctx)
    for step in range(max_depth):
        resp = await llm.chat(messages, tools=tools_for(op_ctx))
        if not resp.tool_calls:
            return resp.content
        for call in resp.tool_calls:
            result = await dispatcher.call(call, op_ctx)
            messages.append(tool_message(call.id, result))
    log.warn("max depth reached")
    return last_response.content or "(em xin lỗi, em hơi loạn)"
```

- Max depth = 5 → ngăn loop dại
- Retry: 2 lần trên transient error (timeout, 5xx, rate-limit)
- Mỗi tool call có timeout (default 30s)
- Log mọi tool call vào `tool_call_log` để debug

### 6.4 Context window management

Mỗi op có "context budget" theo tier model:

| Op | Smart model budget | Cấu trúc context |
|---|---|---|
| NoteUpdater | ~8k tokens | system prompt (~1k) + note hiện tại (~2k) + delta messages (~5k, trim đầu nếu quá) |
| InGroupResponder | ~6k tokens | system prompt (~1k) + group_note (~2k) + retrieval top-20 (~2k) + recent 10 msg (~1k) |
| DMResponder | ~10k tokens | system prompt (~1k) + (group_note nếu hỏi 1 nhóm) (~2k) + retrieval (~3k) + recent DM history (~2k) + tools list (~2k) |

Token counter (tiktoken hoặc provider-native) enforce hard limit. Trim
policy theo thứ tự:
1. Drop messages cũ nhất trong delta
2. Drop retrieval kết quả thấp điểm
3. Truncate group_note giữ section ⚡, 🚧, ✅ (drop 📜 nếu phải)

### 6.5 Mở

- **(mở) Multi-agent cho Phase 2** — khi nào kéo lên? Trigger: nếu single
  agent fail thường xuyên ở task phức tạp.
- **(mở) Tool call caching** — vd `list_groups()` đổi hiếm, có cache 60s?

---

## 7. LLM abstraction

### 7.1 Interface

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

### 7.2 ModelRegistry

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

### 7.3 Router & 2-tier routing

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

### 7.4 Capability gap fallback

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

### 7.5 Cost tracking

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

### 7.6 Mở

- **(mở) Streaming response** — bot reply có stream chunk được không?
  Cải UX cảm giác nhanh. Defer (channel SDK support tricky).
- **(mở) Prompt caching** (Anthropic, OpenAI) — giảm cost khi reuse
  system prompt. Phase 2.

---

## 8. Plugin architecture

### 8.1 Plugin folder

Mỗi plugin = 1 thư mục trong `plugins/`:

```
plugins/
└── google_calendar/
    ├── manifest.toml          # metadata
    ├── tools.py               # tool definitions + handlers
    ├── auth.py                # OAuth start + callback
    ├── settings_schema.json   # config form schema (JSON Schema)
    ├── README.md              # cho user đọc khi enable
    └── assets/
        └── icon.svg
```

### 8.2 Manifest

```toml
# plugins/google_calendar/manifest.toml
id          = "google_calendar"
name        = "Google Calendar"
version     = "0.1.0"
description = "Push action item / deadline thành Calendar event"
icon        = "assets/icon.svg"

[auth]
type        = "oauth2"
scopes      = ["https://www.googleapis.com/auth/calendar.events"]

[capabilities]
tools       = ["create_event", "list_events", "delete_event"]
```

### 8.3 Tools

```python
# plugins/google_calendar/tools.py
from app.plugin_api import tool, ToolContext

@tool(
    name="gcal_create_event",
    description="Tạo Google Calendar event từ action item",
    parameters={
        "type": "object",
        "properties": {
            "title":        {"type": "string"},
            "start_iso":    {"type": "string"},
            "duration_min": {"type": "integer", "default": 30},
            "description":  {"type": "string"},
        },
        "required": ["title", "start_iso"],
    },
)
async def create_event(ctx: ToolContext, title, start_iso, duration_min=30, description=""):
    token    = await ctx.get_oauth_token()
    settings = await ctx.get_settings()   # default_calendar_id, ...
    # call Google API
    ...
    return {"event_id": "...", "url": "..."}
```

Tool prefix `gcal_` tránh collision với core tool / plugin khác.

### 8.4 OAuth flow

```
1. Sếp click "Connect" trên web /plugins/google_calendar
2. Web call plugin.auth.start(boss_id) → trả về URL Google consent
3. Sếp click URL, login Google, accept scopes
4. Google redirect về /api/oauth/plugin/google_calendar/callback?code=...&state=...
5. Endpoint gọi plugin.auth.callback(boss_id, code) → exchange code
   lấy access_token + refresh_token
6. Lưu vào boss_integrations (auth_blob_enc, encrypted)
7. Redirect web về /plugins/google_calendar (đã connected)
```

Schema:

```sql
boss_integrations (
  id              BIGSERIAL PRIMARY KEY,
  boss_id         INTEGER NOT NULL REFERENCES users(id),
  plugin_id       TEXT NOT NULL,
  enabled         BOOLEAN NOT NULL DEFAULT TRUE,
  auth_blob_enc   BYTEA,                  -- encrypted token JSON
  settings_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
  connected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (boss_id, plugin_id)
);
```

### 8.5 Settings auto-render

`settings_schema.json` (JSON Schema chuẩn):

```json
{
  "type": "object",
  "properties": {
    "default_calendar_id": {
      "type": "string",
      "title": "Calendar mặc định",
      "x-enum-from": "list_calendars"
    },
    "auto_push_deadlines": {
      "type": "boolean",
      "title": "Tự đẩy deadline từ group lên Calendar",
      "default": false
    },
    "reminder_minutes": {
      "type": "integer",
      "title": "Nhắc trước (phút)",
      "default": 30,
      "minimum": 0,
      "maximum": 1440
    }
  },
  "required": ["default_calendar_id"]
}
```

Web có generic `<JsonSchemaForm>` (HTMX + Alpine) render thành form HTML.
`x-enum-from` = gọi 1 plugin handler để populate dropdown động (vd list
calendar Google của sếp).

### 8.6 Plugin loading

App startup scan `plugins/`:

```python
plugins_registry: dict[str, Plugin] = {}

for plugin_dir in PLUGINS_ROOT.glob("*/"):
    manifest = load_manifest(plugin_dir / "manifest.toml")
    tools_module = import_module(f"plugins.{plugin_dir.name}.tools")
    auth_module  = import_module(f"plugins.{plugin_dir.name}.auth")
    plugins_registry[manifest.id] = Plugin(manifest, tools_module, auth_module)
```

Thêm plugin = drop folder + restart server. **Không sửa core.**

### 8.7 Per-boss tool composition

Khi build context cho LLM call:

```python
tools = list(CORE_TOOLS)
enabled = await boss_integrations_repo.list_enabled(boss_id)
for inst in enabled:
    plugin = plugins_registry[inst.plugin_id]
    tools.extend(plugin.get_tools(boss_id))
```

Boss A không bật Notion → LLM của boss A không thấy Notion tool. Context
gọn, không hallucinate gọi sai.

### 8.8 Mở

- **(mở) Plugin sandboxing** — plugin code in-process, có quyền đọc DB
  & file system. Phase 0 trust mọi plugin do em viết. Phase 2 nếu mở
  3rd-party → tách process (kiểu MCP) hoặc Wasm.
- **(mở) Plugin version & migrate** — manifest.version tăng → khi nào
  invalidate auth/settings? Hoãn.

---

## 9. Web admin

### 9.1 Auth & session

- **Google OAuth** (primary) qua Authlib. Email/password (fallback) cho
  ai không có Google account.
- Session cookie HTTP-only, Secure, SameSite=Lax, TTL 30 ngày.
- `role` từ `users.role`. Superadmin auto-set khi email trong env
  `SUPERADMIN_EMAILS`.

### 9.2 Sitemap (user pages)

```
/login                   — Google OAuth + email/password
/                        — Dashboard
/groups                  — List group đã capture
/groups/:id              — Group detail (note + history + action items + members)
/action-items            — Tổng hợp action item cross-group
/digests                 — (Phase 1, MVP show "Coming soon")
/channels                — Connect Zalo / Telegram / Lark Messenger
/plugins                 — Marketplace + manage installed
/plugins/:id             — Plugin detail (OAuth + settings form)
/usage                   — Token + cost dashboard
/settings/general        — Tên bot, ngôn ngữ, TZ, retention
/settings/ai             — Provider + model + custom provider
/settings/account        — Email, đổi mật khẩu, đăng xuất
/subscription            — Gói + VietQR + lịch sử thanh toán
```

### 9.3 Sitemap (superadmin pages)

Chỉ visible khi `role=superadmin`:

```
/admin/bosses            — List + detail + set expiry + add payment
/admin/payments          — Log payment + [+ Add payment]
/admin/revenue           — Chart MRR / ARR / top customer
```

### 9.4 Dashboard widgets

```
┌────────────┬────────────┬────────────┬────────────┐
│ N groups   │ K open     │ Digest:    │ Tháng này  │
│ across M   │ action     │ (Coming    │ $X /       │
│ channels   │ items      │  soon)     │ Y M tok    │
└────────────┴────────────┴────────────┴────────────┘
┌──────────────────────────┬──────────────────────────┐
│ Hoạt động 7 ngày qua     │ Cảnh báo                 │
│ [bar chart messages/day] │ • Zalo OA token sắp hết  │
│                          │ • 3 task quá hạn         │
└──────────────────────────┴──────────────────────────┘
```

### 9.5 Group detail page

Mục đích = sếp thấy bot đang làm gì trong group, edit note, scan action item:

```
┌───────────────────────────────────────────────────┐
│ ← Groups · Team Sale Q2                          │
│                                                   │
│ [Note] [History] [Action Items] [Members]        │
│ ───────                                           │
│                                                   │
│ ┌─ Group note ─────────────────────────────────┐ │
│ │ # Team Sale Q2                                │ │
│ │ Cập nhật 30/5 14:32 · 47 msg/ngày             │ │
│ │ ...                                           │ │
│ │ (markdown rendered, click Edit để sửa)        │ │
│ └──────────────────────────────────────────────┘ │
│                                                   │
│ [Edit] [Refresh now] [Export]                    │
└───────────────────────────────────────────────────┘
```

- **Note tab**: render note + Edit/Refresh/Export
- **History tab**: timeline version note + diff view
- **Action Items tab**: filter view của section "Việc đang mở"
- **Members tab**: list người gửi (display name), count message 7d

### 9.6 Channel wizard

Mỗi channel có flow guide ngắn:

```
/channels → [ Connect Zalo ]
  ↓
Modal: "Em sẽ mở Zalo, bot tự DM anh. Anh chỉ tap Gửi."
  ↓ Click "Tiếp"
Deep-link → Zalo app
  ↓ (Sếp tap Gửi message /start <token>)
Bot reply, web detect (poll hoặc Server-Sent Events)
  ↓
Channels page hiện ✓
```

Telegram & Lark Messenger tương tự (URL scheme khác).

### 9.7 Tech stack web

- **Backend**: FastAPI, cùng process với bot
- **Templating**: Jinja2 server-side render
- **Interaction**: HTMX cho partial update (no full SPA)
- **Client state**: Alpine.js cho toggle/dropdown nhẹ
- **CSS**: Tailwind (utility-first)
- **Form**: HTML form + HTMX submit (no React)
- **Charts**: Chart.js trên Usage/Revenue page

Lý do: web admin scale nhỏ (1 sếp = 1 user, ít concurrent), không cần
SPA. HTMX = 1/5 code so với React. Sửa nhanh, dễ ship.

### 9.8 Mở

- **(mở) i18n** — UI tiếng Việt mặc định. Toggle EN có cần? MVP chỉ VN.
- **(mở) Mobile-responsive** — Tailwind breakpoint đủ, không PWA.

---

## 10. Tech stack & infrastructure

### 10.1 Stack

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

### 10.2 Project structure (đề xuất)

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

### 10.3 Deployment (MVP)

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

### 10.4 Env config

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

### 10.5 Observability

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

### 10.6 Mở

- **(mở) Multi-region** — server ở SG/Singapore cho latency Zalo
  webhook + LLM API. Defer.
- **(mở) Backup** — pg_dump cron daily lên S3-compatible. Defer chi tiết.

---

## 11. Tổng hợp open questions

| § | Open question | Em recommend |
|---|---|---|
| 1.7 / 5.4 | Media ingest trong MVP | **B**: URL fetch + voice transcribe |
| 2.5 | Single-process vs split web/worker | Single cho MVP, split khi >50 sếp |
| 3.6 | Nhiều sếp cùng nhóm: tách vs gộp | **Tách** (mỗi sếp 1 note độc lập) |
| 4.7 | Schema 7 section cố định vs cấu hình per-boss | **Cố định** cho MVP |
| 5.7 | Voice STT: API vs tự host | API (Whisper) cho MVP |
| 5.7 | Image OCR | Hoãn Phase 1 |
| 5.7 | Right-to-be-forgotten cá nhân được mention | Hoãn |
| 6.5 | Multi-agent (LangGraph) cho Phase 2 | Defer, theo dõi failure rate |
| 6.5 | Tool call caching | Defer |
| 7.6 | Streaming LLM response | Defer (channel SDK support tricky) |
| 7.6 | Prompt caching Anthropic/OpenAI | Phase 2 |
| 8.8 | Plugin sandboxing | Trust 1st-party MVP, Wasm/MCP nếu mở 3rd-party |
| 8.8 | Plugin version & migrate | Defer |
| 9.8 | i18n web UI | VN-only MVP |
| 9.8 | Mobile responsive | Tailwind breakpoint đủ, không PWA |
| 10.6 | Multi-region | Defer |
| 10.6 | Backup pg_dump cron | Defer chi tiết |

**Cách close questions:**

- Reply ngắn: `media ingest: B` · `nhiều sếp: tách` · `section schema: cố định` · ...
- Hoặc reply 1 message gom tất cả thay đổi anh muốn.
- Hoặc `Spec OK` để duyệt theo em recommend → em commit final + invoke
  `writing-plans` tạo implementation plan.
