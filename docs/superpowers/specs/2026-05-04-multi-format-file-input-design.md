# Multi-format file input — PDF, image, DOCX

**Date:** 2026-05-04
**Status:** Approved (design phase)
**Scope:** Bot reads PDFs, images, and DOCX files inline during conversation. Ephemeral context (≈15-message rolling window via existing `recent_messages`); no persistent storage, no embedding/RAG. Zalo first, Telegram second, CLI for testing.

## Problem

Bot currently accepts only text. `IncomingMessage.attachments` already carries a slot for media, but:

- `telegram.py` detects photo/document and sets `kind` only — no download, `url=""`.
- `zalo.py` (via `bridge.js`) emits a CDN `href` — no download, no mime/filename harvesting.
- No downstream consumer reads `incoming.attachments`. Router → `secretary_agent.handle_message` only takes `incoming.text`.

Boss needs to ask "tóm tắt PDF này", "đọc giúp ảnh menu", "trích lục bảng từ DOCX" — same UX as ChatGPT file upload, lifetime ≈ recent window. Zalo is the priority channel because most customers are on Zalo and forward many files at once.

## Non-goals

- **Persistence/RAG indexing of file contents.** Files are ephemeral; sentinels carrying file references fall out of recent window naturally and are stripped before Qdrant indexing of message text.
- **Voice notes / audio transcription.** Common on Zalo, but separate scope. Whisper pipeline can reuse this design later.
- **OpenAI Responses API + conversation state.** Vendor-locks; conflicts with `LLMClient` provider abstraction in progress on this branch.
- **Per-turn re-encoding of PDFs.** Files API + `file_id` reference is the whole point.
- **Native DOCX ingestion via OpenAI.** Chat Completions does not accept DOCX as `file` content part. We extract to markdown via `mammoth`.
- **Cron-based cleanup.** Replaced by opportunistic local sweep + OpenAI `expires_after`.

## Architecture decisions

| Decision | Choice | Rationale |
|---|---|---|
| LLM API surface | Stay on `chat.completions` | Preserves `LLMClient` Protocol multi-provider work in `infrastructure/llm/`. Responses API would lock to OpenAI. |
| PDF transport | OpenAI Files API → `file_id` reference | Upload once on intake, reference each turn for ~15 turns. Avoids re-encoding 1-30MB PDFs every call. |
| Image transport | Local file + base64 inline per turn | `chat.completions` `image_url` content part takes data URI reliably. Re-encode cost negligible (image << PDF). |
| DOCX transport | `mammoth` → markdown inline in user text | OpenAI does not accept DOCX as native file content part. Mammoth preserves headings/lists/table structure better than `python-docx`. Pure Python, no Docker dep. |
| File reference encoding | Single-line text sentinel in `messages.content` | Zero schema migration. Sentinel format `[OPENAI_FILE: ...]` / `[LOCAL_IMAGE: ...]`. Parser at LLM call site converts to OpenAI content parts. |
| Cleanup strategy | Opportunistic local sweep (>24h on each ingest) + OpenAI `expires_after=2592000s` | No cron. Idempotent. Self-healing across crashes. |
| Sentinel-aware components | `infrastructure/llm/openai.py` (parse → parts), Qdrant indexer (`strip_sentinels` before embed) | Keeps OpenAI-specific knowledge in OpenAI provider. Future Anthropic/Gemini providers translate sentinels into their own schema. |
| Channel ownership of download | Each channel adapter | Zalo: bridge.js downloads with active session cookies (CDN may 403 for unauthed Python fetch). Telegram: Python downloads via bot token `getFile`. |

## Pipeline

```
┌── ZALO ──────────────┐    ┌── TELEGRAM ─────────┐    ┌── CLI (test) ───┐
│ bridge.js            │    │ telegram.py         │    │ cli_test.py     │
│ • zca-js session     │    │ • bot token         │    │ • --attach flag │
│ • node-fetch href    │    │ • getFile + GET     │    │ • copy local    │
│ • save to            │    │ • save to           │    │   file in       │
│   data/inbound/<...> │    │   data/inbound/<...>│    │                 │
│ • emit {kind, mime,  │    │ • build Attachment  │    │                 │
│   filename, size,    │    │   full fields       │    │                 │
│   local_path}        │    │                     │    │                 │
└──────────┬───────────┘    └──────────┬──────────┘    └────────┬────────┘
           │                           │                        │
           ▼ zalo.py harvest           ▼                        ▼
       Attachment(url=local_path, mime_type, filename, size_bytes)
                                       │
                                       ▼
                ┌──────────────────────────────────────────────┐
                │ NEW src/agent/file_ingestion.py              │
                │   async ingest(attachments) → str            │
                │                                              │
                │   asyncio.gather over attachments:           │
                │   • image/*           → sentinel             │
                │     [LOCAL_IMAGE: path=... mime=...]         │
                │   • application/pdf   → upload Files API     │
                │     (expires_after=30d) → sentinel           │
                │     [OPENAI_FILE: file_id=... mime=...       │
                │      filename=...]; xoá local sau upload     │
                │   • DOCX              → mammoth → markdown   │
                │     truncate 20KB; xoá local sau extract     │
                │   • khác              → "[Tệp X — chưa hỗ    │
                │     trợ định dạng .xxx]"                     │
                │                                              │
                │   opportunistic sweep: xoá file >24h trong   │
                │   data/inbound/<conv_id>/                    │
                └──────────────────┬───────────────────────────┘
                                   ▼
   user_text = original_text + "\n\n" + ingested_text
                                   ▼
   secretary_agent saves to messages.content (TEXT, sentinel inside)
                                   ▼
   build messages list as today; pass to LLMClient.chat_with_tools
                                   ▼
   infrastructure/llm/openai.py: walk messages, regex-replace sentinels
   on their own line → content parts list:
     [{type:"text", text:<sentinel-stripped>}, <file/image parts>]
                                   ▼
   chat.completions.create(messages=[...])
                                   ▼
   After 15 messages, sentinel rolls out of recent_messages window
   → bot naturally "forgets" the file
```

## Sentinel format

Each sentinel **must** occupy its own line. Parser uses multiline regex `^\[(OPENAI_FILE|LOCAL_IMAGE):\s+([^\]]+)\]$`. Inline-typed `[OPENAI_FILE: ...]` inside boss text won't match.

```
[OPENAI_FILE: file_id=file-xxx mime=application/pdf filename=invoice.pdf]
[LOCAL_IMAGE: path=data/inbound/abc/123_photo.jpg mime=image/jpeg]
```

Rendered text shown to model after parsing:

```
<text gốc của boss với sentinel removed>
```

Plus content parts appended:
- `{"type":"file","file":{"file_id":"file-xxx"}}` for OPENAI_FILE
- `{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}` for LOCAL_IMAGE (re-read disk + b64 each turn)

If `LOCAL_IMAGE` path no longer exists (window rolled / file purged): replace with text `[Ảnh đã hết hạn]` so model doesn't crash.

## Components

### New files

| File | Responsibility |
|---|---|
| `src/agent/file_ingestion.py` | `async ingest(attachments: list[Attachment]) -> str`. Dispatch by mime, emit sentinels / inline markdown, run opportunistic sweep. |
| `src/infrastructure/openai_files.py` | `async upload(path, mime, filename) -> file_id` (with `expires_after=2592000s`). `async delete(file_id)` for ad-hoc cleanup. Retry: 3 attempts exponential backoff (200ms, 1s, 5s) on 5xx/429/network. |
| `src/utils/sentinels.py` | `strip_sentinels(text) -> str` (used by Qdrant indexer). `parse_sentinels(text) -> (cleaned_text, refs)` (used by OpenAI provider). |

### Modified files

| File | Change |
|---|---|
| `src/channels/zalo_bridge/bridge.js` | When `attachments[].href` present: `node-fetch` with active Zalo session, save to `data/inbound/<thread_id>/<msg_id>_<sanitized_filename>`. Best-effort harvest of mime/filename/size from `data.content.params` (fields like `fileName`, `fileExt`, `totalSize` per zca-js); fallback to URL extension + `mimetypes` lookup; for image messages default to `image/jpeg` if no extension info. Emit `{kind, mime, filename, size_bytes, local_path}` (replaces `href`). On fetch failure: emit `{..., error: "<reason>"}` instead. |
| `src/channels/zalo.py` | Map bridge output → `Attachment(url=a["local_path"], mime_type=a["mime"], filename=a["filename"], size_bytes=a["size_bytes"])`. If `error` field present: `Attachment(kind=..., filename=..., url="")` so ingest emits the right sentinel. |
| `src/channels/telegram.py` | After detecting photo/document, call Telegram `getFile` → fetch bytes from `https://api.telegram.org/file/bot<token>/<path>` → save to `data/inbound/<chat_id>/<msg_id>_<filename>` (photo filename auto-gen from `file_unique_id` + `.jpg`, mime default `image/jpeg`). Populate full `Attachment` fields. |
| `src/agent/secretary_agent.py` | `handle_message` accepts `attachments` param. Before saving user message + building LLM messages: `ingested = await file_ingestion.ingest(attachments)`; if non-empty, `text = original_text + "\n\n" + ingested`. RAG search uses original text (pre-enrichment). DB save + LLM messages use enriched text. |
| `src/controllers/message_router.py` | Pass `incoming.attachments` through to `handle_message`. |
| `src/infrastructure/llm/openai.py` | In `chat_with_tools`, pre-process `messages`: each message whose `content` is `str`, run `parse_sentinels(content)`. If refs found, replace `content` with parts list `[{type:"text", text:cleaned}, ...refs]`. No-op if no sentinels. |
| `src/repositories/message_repo.py` (or wherever Qdrant indexing lives) | Before passing message text to `cohere.embed` for Qdrant upsert: call `strip_sentinels(content)`. |
| `src/channels/cli_messenger.py` + `scripts/cli_test.py` | Add `--attach <path>` CLI flag, build `Attachment` from local file (mime via `mimetypes.guess_type`), feed into IncomingMessage. For test parity. |
| `pyproject.toml` | Add `mammoth>=1.6`, `pypdf>=4.0` (encrypted-PDF pre-check). Note: Zalo mime detection uses `mimetypes` stdlib + extension parsing; no `python-magic` needed. |
| `Dockerfile` | Ensure `data/inbound/` dir exists (already mounted via `data/` volume). No new system packages required. |
| `src/channels/zalo_bridge/package.json` | Add `node-fetch@^3` dependency. |

## Limits & error handling

| Failure mode | Behaviour |
|---|---|
| Image > 20MB | Skip upload, sentinel `[Tệp <name> — ảnh quá to (>20MB)]` |
| PDF > 32MB or > 100 pages | Reject pre-upload, sentinel `[Tệp <name> — PDF quá lớn]` |
| DOCX > 5MB file or markdown output > 20KB | Convert + truncate at 20KB chars + suffix `\n…(file dài, em chỉ đọc ~10 trang đầu)` |
| Encrypted PDF | `pypdf.PdfReader(path).is_encrypted` pre-check → sentinel `[Tệp <name> — file có password]` |
| Encrypted DOCX | mammoth raises → catch → same sentinel |
| Telegram getFile / Zalo CDN fetch fail | log + sentinel `[Tệp <name> — không tải được]` |
| OpenAI Files API 4xx | sentinel `[Tệp <name> — lỗi định dạng]` |
| OpenAI Files API 5xx / 429 / network | retry 3× backoff; final fallback `[Tệp <name> — tạm thời lỗi, gửi lại giúp anh]` |
| Unknown mime | sentinel `[Tệp <name> — chưa hỗ trợ định dạng .xxx]` |
| Local image file gone at LLM call | content part replaced with text `[Ảnh đã hết hạn]` |
| Vietnamese filename | `unicodedata.normalize('NFC', name)` + `re.sub(r'[/\\<>:"|?*\x00-\x1f]', '_', name)` + truncate base name 80 chars, keep extension |
| Multiple files in 1 turn | `asyncio.gather`; partial failure does not abort the rest |
| Crash mid-ingest | Local orphan: opportunistic 24h sweep on next ingest. OpenAI orphan: `expires_after` purges in 30d. |
| Sentinel typed by boss inline | Parser only matches when sentinel is the entire line; inline `[OPENAI_FILE: ...]` left untouched. |

## Testing

### Unit

`tests/agent/test_file_ingestion.py`
- `ingest([])` → `""`
- Image attachment → `[LOCAL_IMAGE: ...]` exact format
- PDF → mock `openai_files.upload` → `[OPENAI_FILE: ...]`; local file deleted post-upload
- DOCX → mock `mammoth.convert_to_markdown` returning 50KB → output truncated at 20KB + suffix note
- Unsupported mime (`application/zip`) → unsupported sentinel
- 3 attachments concurrent: order stable, 1 fail does not block others
- Filename `Báo cáo Q1/2026.docx` → sanitized `Báo cáo Q1_2026.docx`
- Encrypted PDF → fail fast pre-upload
- 33MB PDF → reject pre-upload

`tests/utils/test_sentinels.py`
- `strip_sentinels`: removes whole-line sentinels, leaves inline-typed ones
- `parse_sentinels`: no sentinel → `(text, [])`; multi sentinel → cleaned text + N refs
- Inline `[OPENAI_FILE:...]` mid-sentence → not parsed

`tests/infrastructure/llm/test_openai_provider.py`
- `chat_with_tools` with sentinel-bearing message → content parts emitted match OpenAI schema
- Local image path missing at call time → text fallback `[Ảnh đã hết hạn]`

### Integration

- Telegram: mock `getFile` API + mock bytes → `IncomingMessage.attachments[0]` has correct `url`/mime/filename
- Zalo bridge: `node scripts/test_bridge_attachment.js` with mock zca-js message JSON containing `params.fileName`/`fileExt` → bridge emits `local_path`
- Both channels normalize identically from `Attachment` onward

### End-to-end smoke (manual)

1. Zalo: send PDF 5 trang + caption "tóm tắt giúp" → bot trả lời với nội dung
2. Follow-up "phần thanh toán nói gì?" → bot vẫn thấy file (file_id còn trong window)
3. Send 16 unrelated messages → ask about file again → bot không còn nhớ ✓
4. Telegram: repeat 1-2
5. Send `.xlsx` → bot replies "chưa hỗ trợ Excel"
6. Send PDF scan-only → OpenAI attempts; if fails → graceful reply
7. Send DOCX 50 trang → bot acknowledges "đã đọc 10 trang đầu"
8. Group chat (Zalo) where bot is mentioned per existing routing: boss shares PDF → bot reads file as in DM; follow-up @mentions in same group still see file while window holds

### Regression

- Text-only chat (no attachments): flow unchanged. Sentinel parser is no-op.
- Tool calling (`add_reminder`, `add_note`, etc.): works inside file-bearing turns.
- Onboarding flow: unaffected (no file ingestion path).

## Implementation order

1. **Sentinel utils + tests** (`src/utils/sentinels.py`) — pure logic, no deps.
2. **OpenAI Files wrapper + tests** (`src/infrastructure/openai_files.py`) — mockable.
3. **`file_ingestion` module + tests** — wired to mocks; covers all mime branches, caps, errors.
4. **`infrastructure/llm/openai.py` sentinel parsing** — extends provider.
5. **Qdrant indexer strip_sentinels integration** — defensive against polluted vectors.
6. **Zalo channel** — bridge.js download + zalo.py mapping; smoke test on staging account.
7. **Telegram channel** — getFile download + telegram.py mapping.
8. **secretary_agent + message_router wiring** — pass attachments through.
9. **CLI `--attach` flag** — local test parity.
10. **End-to-end smoke** — both channels, all mime paths.
