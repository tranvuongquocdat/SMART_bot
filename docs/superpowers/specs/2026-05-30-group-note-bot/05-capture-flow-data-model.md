[← Index](./README.md)

# §5. Capture flow & Data model

## 5.1 Pipeline nhận message

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

## 5.2 Schema `messages`

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

## 5.3 Indexing: FTS + Qdrant

**Postgres FTS:**
- Dùng cho keyword lookup ("có ai nói X không").
- Tiếng Việt: config `simple` + extension `unaccent` + `pg_trgm` để
  match không phân biệt dấu.
- Index trên `text` và `media_text`.

**Qdrant:**
- **1 collection duy nhất**, filter qua payload `boss_id`. Tránh
  overhead quản N collection. Boss-filter chạy nhanh.
- Embedding: `text-embedding-3-small` (1536 dims) cho MVP. Switch được
  qua LLM-abstraction ở [§7](./07-llm-abstraction.md).
- Granularity: **per-message** cho MVP. Message Zalo phần lớn ngắn.
  Paragraph chunking hoãn.
- Payload: `{boss_id, provider, chat_id, ts, sender_name}` để filterable.

**Hybrid retrieval (Q&A):**
```
1. FTS pre-filter (boss_id, chat_id?, optional date range) → ≤500 candidate
2. Vector rank top-20 trong đó (Qdrant với payload filter)
3. Pass cho LLM cùng group_note hiện tại
```

## 5.4 Xử lý media — decision mở

| Option | MVP có gì | Effort | Risk nếu skip |
|---|---|---|---|
| **A. Chỉ text** | Voice / image / file / URL lưu `media_kind` + `media_url`; `media_text` rỗng. Note bỏ qua. | 0 | Note miss ~30–50% content của group Zalo SME điển hình. |
| **B. URL fetch + voice transcribe** | `media_text` populate cho URL (body fetched) và voice (Whisper-style transcribe). Note cover content của chúng. | +2 tuần | Image OCR + file extract vẫn thiếu — gap nhỏ hơn. |
| **C. Full media ingest** | A + B + OCR ảnh + extract PDF/docx. | +4 tuần | Ship chậm. |

Recommendation: **B**. Group Zalo voice-heavy → cost xứng đáng. Image /
file để Phase 1.

## 5.5 Lưu trữ & quyền riêng tư

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

## 5.6 Log message gửi đi

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

## 5.7 Mở

- **(mở) Voice transcription** — API (OpenAI/Groq Whisper) vs tự host
  (whisper.cpp). Em recommend API cho MVP.
- **(mở) Image OCR** — hoãn Phase 1.
- **(mở) Quyền "xoá tôi khỏi data" cho cá nhân được mention** — hoãn.
