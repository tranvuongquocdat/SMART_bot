# Design — Đọc link/media + web_search + Integration superadmin

> Spec gộp (user chốt 1 spec to). Brainstorm 2026-06-19. Nhánh "gỡ cứng nhắc" của project,
> phần C (đọc link/media). Tham chiếu trạng thái nền: `docs/architecture/system-design.md`.

## 1. Bối cảnh & mục tiêu

Bot hiện "đọc link bị reject" và không tra web được, dù `fetch_url` tồn tại và module
`src/media/` đã được build gần xong. Nguyên nhân gốc: **module media chưa được cắm dây**
(`src/media/adapters/__init__.py` rỗng → adapters không tự đăng ký → `find_adapter` luôn
fail → `fetch_url` rơi về HTTP-strip thô). Ngoài ra chưa có tool `web_search`.

**Mục tiêu:** bot đọc được mọi link/media người dùng đưa (web/báo, YouTube transcript,
TikTok best-effort, PDF/DOCX/XLSX, ảnh) **và** tự tra web (web_search), với key/usage/chi phí
quản lý tập trung ở superadmin (có biểu đồ + báo lỗi key trên trang).

**Nguyên tắc:** tái dùng tối đa lớp `src/media/` đã có (deps đã cài: trafilatura, yt-dlp,
pypdf, python-docx, openpyxl, pillow, pillow-heif; bảng `media_cache` + vision model slot +
caps routing đã có). Đây là việc **hoàn thiện + cắm dây**, không phải build mới.

## 2. Non-goals (ranh giới)

- **Voice/ASR** (transcribe audio/video): để phase sau (user đã chốt). ⇒ TikTok/video chỉ
  best-effort (metadata + phụ đề-nếu-có), **không** transcript đầy đủ.
- **Per-boss search key:** v1 chỉ platform key (superadmin). Boss không tự mang key Tavily.
- **Refactor platform LLM-key (OpenAI/Groq) sang DB/superadmin UI:** ngoài phạm vi (tránh đụng
  WIP AI-settings). Chỉ làm key của provider SEARCH trong mục "Integrations" mới.
- **Đổi responder sang multimodal thật:** không cần — vision call nằm gọn trong ImageExtractor,
  trả về TEXT (`media_text`), responder vẫn xử text.

## 3. Kiến trúc & luồng dữ liệu

Lớp `src/media/` (registry + adapters) là **nguồn DUY NHẤT** biến mọi artifact → text.
Hai đường vào, cùng gọi lớp này:

```
Đường A (on-demand):   responder ──tool── fetch_url(url) / web_search(query) ──▶ media layer ──▶ text
Đường B (đính kèm):    message.captured (có media_url) ──enrichment(async)──▶ media layer ──▶ media_text (DB)
```

- **web_search** trả danh sách kết quả {title, url, snippet, content}; bot đọc sâu thêm bằng
  `fetch_url` khi cần.
- Vision: ImageExtractor tự gọi vision-LLM → trả text → inject như text thường (cả 2 đường).

## 4. Component 1 — Media extraction layer (`src/media/`)

**4.1 Wire-up (bug gốc).** `adapters/__init__.py` import cả `web`, `document`, `image` để
`@media_adapter` chạy → `_ADAPTERS` được populate. (Đảm bảo nơi nào dùng `find_adapter` cũng
đã import `src.media.adapters`.)

**4.2 WebExtractor — YouTube transcript thật.** Hiện `_pick_subtitle` cố tình `return None`
→ chỉ lấy được description. Sửa: thêm dep `youtube-transcript-api`; lấy transcript (ưu tiên
`vi` → `en`, cả auto-sub) ghép thành text; fallback description nếu không có. **Caveat:**
YouTube hay chặn IP datacenter khi gọi từ server → bắt lỗi gọn, fallback (yt-dlp/description),
**không crash**; ghi log để theo dõi tần suất block (cân nhắc proxy ở phase sau nếu block nhiều).

**4.3 WebExtractor — TikTok best-effort.** Hiện `tiktok` rơi vào `_generic` (trafilatura trên
HTML TikTok → kém). Tách route riêng: dùng yt-dlp lấy title/description/phụ-đề-nếu-có. Transcript
đầy đủ = ASR phase sau (ghi rõ giới hạn trong kết quả nếu rỗng).

**4.4 DocumentExtractor.** Đã đủ (pdf/docx/xlsx/txt). Cần caller (fetch_url / enrichment)
truyền `content` bytes + `content_type` (adapter không tự fetch document).

**4.5 ImageExtractor.** Đã đủ (HEIC→JPEG, lọc sticker, cache theo hash, gọi vision-LLM,
`requires_caps={"vision"}`). Cần: (a) caller truyền `llm_gateway`+`pool`+`boss_id`; (b) boss có
`vision_model_id` cấu hình + caps routing có model "vision" — nếu thiếu → trả text rỗng (degrade,
không crash). ImageExtractor tự fetch bytes từ URL được rồi.

## 5. Component 2 — `fetch_url` viết lại (`src/tools/core/web.py`)

Thay toàn bộ thân hàm. Luồng:

1. Detect kind: registry `_detect_from_url` (youtube/tiktok/url). Nếu url có đuôi file
   (pdf/docx/xlsx/txt) hoặc 1 GET trả `content-type` document/ảnh → kind = document/image.
2. Nếu cần bytes (document/image): tải bytes (httpx, follow_redirects, timeout, cap kích thước),
   gọi adapter với `content`+`content_type`. Web/youtube/tiktok: adapter tự xử (không cần bytes).
3. Ảnh: inject `llm_gateway`+`pool`+`boss_id` từ `ToolContext`. **Cần verify `ToolContext` expose
   được LLM gateway**; nếu chưa → thêm field (đây là điểm rủi ro tích hợp đã biết).
4. Trả `{title, text}` (cap = `MAX_BODY_BYTES` = 50KB, 1 nguồn duy nhất cho mọi adapter) **hoặc error rõ ràng**
   ("link cần đăng nhập", "không tải được", "định dạng không hỗ trợ"). Bỏ hẳn nhánh "HTTP strip"
   cũ — generic giờ qua trafilatura.

`fetch_url` vẫn là 1 tool đồng bộ (gọi trong responder loop, có timeout). yt-dlp/transcript chậm
nhưng chấp nhận được trong tool-call với timeout hợp lý.

## 6. Component 3 — Inbound attachment enrichment (đường B)

Khi `message.captured` có `media_url` (kind ≠ text): chạy bước enrichment **async off hot-path**
(không chặn ingest) → media layer → điền `media_text` vào row message. Spine extract + responder
đọc `media_text` như text thường (đã có sẵn cột `media_text`, hiện luôn None).

- Cache theo hash (media_cache) → ảnh/file trùng không tốn vision token / xử lý lại.
- Degrade: lỗi extract → `media_text` rỗng, log, không ảnh hưởng luồng tin nhắn.
- ⚠️ **Test:** web test channel chỉ có text → đường B verify bằng **fixture** (chèn message có
  `media_url` trỏ tới file/ảnh thật trên CDN/local) hoặc khi cắm Zalo. Đường A test ngay được.

## 7. Component 4 — `web_search` tool + provider (Tavily, pluggable)

- **Interface** `SearchProvider.search(query, *, max_results) -> list[SearchResult]` với
  `SearchResult{title, url, snippet, content}`. Impl `TavilyProvider` gọi REST Tavily qua `httpx`
  (KHÔNG thêm SDK nặng). Pluggable để sau đổi Serper/Brave.
- **Tool** `web_search` (core, `available_to={"dm_responder","in_group_responder"}`), đăng ký vào
  `tools={...}` 2 responder. Trả kết quả gọn; pattern: search → đọc sâu bằng `fetch_url`.
- **Lấy key/đơn giá** từ bảng `platform_integrations` (mục 8). Thiếu/lỗi key → tool trả error
  "chưa cấu hình tìm kiếm" / "key tìm kiếm lỗi" (không crash) **và** cập nhật `status` để trang
  superadmin báo đỏ.
- Mỗi call → ghi usage + cost (mục 8).

## 8. Component 5 — Integration superadmin (key · health · cost · charts)

**8.1 Data model (migration mới).**
- `platform_integrations`: `provider TEXT PK` (vd 'tavily'), `api_key_enc TEXT` (Fernet, tái dùng
  `src/llm/api_keys.py::_fernet`), `unit_cost_usd NUMERIC` (đơn giá/1 query, superadmin nhập tay),
  `status JSONB` `{ok, message, checked_at}` (mirror `ai_key_status`), `updated_at`.
- `integration_usage`: ghi để vẽ chart. Daily-rollup upsert `{provider, boss_id, day} → count,
  cost_usd` (gọn hơn per-call). Cho phép tổng + theo ngày + theo boss.

**8.2 Endpoints superadmin** (`require_superadmin`):
- `GET /api/v1/superadmin/integrations` → list provider + status + unit_cost + tổng usage/cost.
- `PUT .../integrations/{provider}` → set api_key (mã hoá) + unit_cost.
- `POST .../integrations/{provider}/test` → gọi Tavily 1 query rẻ để validate → ghi `status`
  (mirror `api_ai test-key`).
- `GET .../integrations/{provider}/usage?range=` → totals + daily (cost/count) + by-boss → cho charts.

**8.3 FE superadmin** (tái dùng `charts.tsx` + mẫu trang Usage):
- Mục "Tích hợp / Tìm kiếm web": input key + nút **"Kiểm tra"** + badge trạng thái (xanh/đỏ +
  message + checked_at) + input `unit_cost`.
- Card tổng (số query · tổng chi phí · trạng thái key) + **BarChart chi phí theo ngày** +
  RankBars theo boss. i18n vi/en.

**8.4 Runtime ghi usage:** `web_search` mỗi call → upsert `integration_usage` (count+1,
cost += unit_cost). Lỗi key (401/quota) → cập nhật `status.ok=false`+message.

## 9. Component 6 — Prompt (responder + extractor)

- Responder `dm_general` + `in_group` (bump version): "Khi tin có URL hoặc cần thông tin NGOÀI
  kho tri thức → **CHỦ ĐỘNG** gọi `fetch_url` (đọc link) / `web_search` (tra web). **KHÔNG** tự
  nói 'không đọc được link' khi chưa thử. Tóm tắt **ngắn gọn, đúng trọng tâm** (đang trả lời quá
  dài khi phân tích link/video)." Giữ đồng bộ vi/en + reseed.
- (Tùy) extractor: `media_text` có nội dung → coi như nguồn tri thức hợp lệ.

## 10. Error handling (xuyên suốt)

- Mọi adapter degrade về `media_text=""` / error message, **không crash** responder/ingest.
- `fetch_url` luôn trả error message hữu ích thay vì im lặng.
- web_search thiếu/lỗi key → error gọn + cập nhật status trên trang superadmin.
- Vision thiếu model → text rỗng (không lỗi cứng).
- YouTube IP-block → fallback + log.

## 11. Testing

- **Đường A (test ngay trên web test channel):** harness — paste link bài báo → bot tóm đúng;
  paste YouTube → bot tóm theo transcript; `web_search` câu hỏi tin tức → bot trả lời + dẫn nguồn.
- **Đường B (fixture):** chèn message có `media_url` (PDF/ảnh thật) → enrichment điền `media_text`
  → bot trả lời dựa trên nội dung file/ảnh.
- **Unit test mỗi adapter:** fixture HTML/PDF/DOCX/XLSX/ảnh nhỏ → assert text trích đúng; YouTube/
  TikTok mock (tránh phụ thuộc mạng/anti-bot trong test).
- **Integration superadmin:** test set/get key (mã hoá), test-key (mock provider), usage rollup +
  endpoint usage trả số đúng; FE build sạch.
- **Regression:** giữ `gold`/`multipass`/`workload` xanh.

## 12. Migrations & deps

- Deps: `+youtube-transcript-api`. (Tavily qua httpx; media deps khác đã cài.)
- Migration mới: `platform_integrations` + `integration_usage`. (`media_cache` đã có.)

## 13. Thứ tự thực thi (gợi ý cho plan)

1. Wire adapters + `fetch_url` viết lại (đường A, web/youtube/pdf) → **gỡ ngay nỗi đau "đọc link
   bị reject"**, test được.
2. TikTok best-effort + ảnh (vision) qua fetch_url.
3. `web_search` tool + TavilyProvider (key tạm qua .env để chạy) → test đường A đầy đủ.
4. Integration superadmin: bảng + endpoints + FE (key/health/cost/charts) → chuyển key sang DB.
5. Đường B (enrichment đính kèm) + prompt responder + extractor.
6. Unit tests + regression.

## 14. Rủi ro / điểm cần xác nhận khi implement

- `ToolContext` có expose LLM gateway cho ImageExtractor không (nếu chưa → thêm).
- YouTube IP-block từ server (có thể cần proxy ở phase sau).
- Vision model: boss cần `vision_model_id` + caps routing có model vision (gpt-5.4-mini xác nhận
  vision-capable trước khi dựa vào).
- Cost charts: chọn daily-rollup vs per-call (spec đề xuất daily-rollup cho gọn).
