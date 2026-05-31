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
  media_kind         TEXT,                 -- NULL | 'url' | 'youtube' | 'tiktok' | 'pdf' | 'docx' | 'xlsx' | 'image' | 'voice' | 'sticker' | 'file'
  media_url          TEXT,                 -- nơi fetch
  media_text         TEXT,                 -- text extract (xem §5.4)

  ts                 TIMESTAMPTZ NOT NULL, -- timestamp của platform
  ingested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  fts                tsvector,             -- update qua trigger

  UNIQUE (provider, chat_id, provider_msg_id)
);
CREATE INDEX idx_messages_chat ON messages(boss_id, provider, chat_id, ts DESC);
CREATE INDEX idx_messages_fts ON messages USING GIN(fts);
```

**Lưu ý:**
- `media_text` là text equivalent để search. URL → body bài báo fetched.
  YouTube → transcript. PDF/docx/xlsx → text extract. Voice + image OCR
  hoãn Phase 1. FTS index cả `text` và `media_text`.
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

## 5.4 Media ingest

**Port từ legacy** — code cũ đã có sẵn các adapter này, MVP tận dụng
thay vì viết lại. Mỗi loại media wrap thành 1 tool/handler, kết quả lưu
vào `messages.media_text`:

| Loại | Adapter (legacy) | Output → `media_text` |
|---|---|---|
| **URL bài báo / blog** | `httpx + trafilatura` | full body sạch, ~5–20k char |
| **YouTube link** | `yt-dlp` lấy transcript (auto-caption) | transcript đầy đủ |
| **TikTok / video URL** | legacy fetch → caption + comment top | metadata + text |
| **PDF attached** | legacy `pypdf` | text extract, ≤20 trang |
| **DOCX attached** | legacy `mammoth` → markdown | text extract, ≤20KB out |
| **XLSX attached** | `openpyxl` | text extract |
| **Plain text file** | UTF-8 decode | inline, ≤20KB out |
| **Image** (jpeg/png/webp/gif/heic/heif) | legacy HEIC→JPEG + mime sniff + **vision-LLM extract-once** | description + OCR text trong 1 call |
| **Voice note** | bỏ qua MVP — `media_text` rỗng | (Phase 1 transcribe) |
| **Sticker** | skip — `media_text` rỗng | không có giá trị note |

### Image extract-once

Khác legacy passthrough (ảnh re-base64 mỗi turn LLM):

```
Inbound image
  ▼
HEIC/HEIF → JPEG convert (Pillow + pillow_heif, port legacy)
  ▼
Filter skip nếu:
  - size < 50KB (sticker/emoji)
  - dimension < 200×200 (icon)
  - mime sticker-specific
  ▼
Cache lookup theo content-hash sha256(bytes)
  hit → reuse media_text
  miss:
    ▼
    Vision-LLM call (1 lần, fast-tier vision)
    Prompt: "Mô tả ngắn ảnh này (1–3 câu) và trích xuất text
             nếu có (OCR). Bỏ qua sticker/meme."
    ▼
    Output: {description, ocr_text}
    media_text = "[image] {description}\n{ocr_text}"
    ▼
    INSERT media_cache (source_key=hash, source_kind='image', ...)
```

Lý do extract-once:
- Group note rebuild không tốn LLM call cho ảnh (chỉ đọc text đã trích).
- Search (FTS + Qdrant) tìm được ảnh qua mô tả + OCR.
- Ảnh forward giữa group / lặp → cache hit, 1 image = 1 call duy nhất.

Cost guard:
- Dùng **vision-tier model** (fast vision: gpt-4o-mini, gemini-flash), không smart-tier.
- Sếp config vision model riêng ở `/settings/ai`
  ([§9.2](./09-web-admin.md#92-sitemap-user-pages)).
- Rate-limit `image_extract` ở [§12.4](./12-security.md#124-rate-limit-interface):
  default 100 ảnh/giờ/sếp.

### Nguyên tắc chung

- Adapter chạy **async sau khi webhook ack**. Không block.
- Timeout per adapter: 30s URL fetch, 60s YouTube transcript, 30s file
  parse, 20s image vision-LLM. Quá → log + giữ `media_text` rỗng, không
  retry tự động.
- Cache theo `media_url` (URL ngoài) + content-hash (file/image attached) —
  cùng URL/ảnh gửi nhiều group không fetch/extract lại.
- Truncate `media_text` ở 50k char trước khi index FTS + Qdrant.
- Tool agent (`@bot phân tích link này` / `@bot ảnh này nói gì`) gọi
  cùng adapter nhưng synchronous trong agent loop (timeout giảm còn 20s,
  vision có thể bump lên smart-tier khi agent gọi tay).

### Bảng cache

```sql
media_cache (
  id              BIGSERIAL PRIMARY KEY,
  source_key      TEXT NOT NULL,        -- URL chuẩn hoá hoặc sha256(file)
  source_kind     TEXT NOT NULL,        -- 'url' | 'youtube' | 'pdf' | 'docx' | 'xlsx' | 'tiktok'
  media_text      TEXT NOT NULL,
  title           TEXT,
  fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at      TIMESTAMPTZ,          -- NULL = vĩnh viễn cho file; URL = 30d
  UNIQUE (source_key, source_kind)
);
CREATE INDEX idx_media_cache_expires ON media_cache(expires_at);
```

Voice + OCR đẩy Phase 1 (xem [§1.5](./01-product-vision-scope.md#15-hoãn-phase-1)).

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

## 5.7 Đã chốt & hoãn

- Media MVP = URL / YouTube / TikTok / PDF / docx / xlsx / **image (vision-LLM extract-once)** (port legacy + thêm vision call).
- Voice → Phase 1.
- "Xoá tôi khỏi data" cho cá nhân được mention → Phase 1+ (chờ user request thực).
