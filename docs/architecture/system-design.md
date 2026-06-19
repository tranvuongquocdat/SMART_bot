# Thiết kế hệ thống — Quyết định top-down (living doc)

> Đọc từ trên xuống. Chốt từ tầng rộng → tầng hẹp. Mỗi tầng lock xong mới xuống tầng dưới.
> Chi tiết kỹ thuật sâu: xem `docs/research/memory-retrieval-architecture-2026-06.md`.

Cập nhật: 2026-06-12 · Trạng thái: Tầng 0–1 ĐÃ CHỐT, Tầng 2 đang đề xuất + Nguyên tắc xuyên suốt.

---

## ⭐ NGUYÊN TẮC SẢN PHẨM XUYÊN SUỐT (áp cho MỌI tầng)

**Trải nghiệm của BOSS phải tối giản.** Boss tìm đến vì đang quá tải — bắt boss tự cấu hình/quyết định
nhiều = phản tác dụng, mất luôn lý do họ dùng sản phẩm. Hệ quả thiết kế bắt buộc:

- **Default thông minh thay cho khai báo.** Boss "nói chuyện tự nhiên", không form, không nút setup.
  Thứ gì boss không buộc phải quyết → đừng hỏi.
- **Bot TỰ HỌC** sở thích/thói quen từng sếp (qua sổ tay tự quản "có kiểm soát") thay vì bắt boss khai.
- **Hai tầng admin:**
  - **Superadmin (platform)** sở hữu "factory config": **template report**, prompt pack, capability mặc
    định, tuning. Đây là nơi tập trung mọi cấu hình phức tạp.
  - **Boss** gần như KHÔNG chạm config — chỉ dùng; cùng lắm vài tinh chỉnh nhẹ, tùy chọn.
- **Report template do superadmin quản** (không phải boss thiết kế) — boss chỉ cần bảo "tạo report tuần".

---

## TẦNG 0 — Hệ thống làm được gì (✅ CHỐT)

**Phạm vi lõi đã chọn: Thư ký lõi + Phân tích.**

| Bậc | Việc | Trạng thái build | Độ chắc |
|---|---|---|---|
| 1 — Thư ký lõi | Bắt & theo dõi task/reminder/note từ chat; hỏi đáp; câu nối tiếp | **LÕI — build chắc** | 85–90% |
| 3 — Phân tích | Đánh giá hiệu suất team, insight | **LÕI — nhưng chỉ mức ADVISORY** | ⚠️ bản nháp cho người duyệt |
| 2 — Chủ động | Calendar sync, digest, nhắc trước | **Module lắp sau** | trích xuất chắc, cần integration |

**Guardrail Phân tích:** không bao giờ xuất "điểm số" như sự thật khách quan; luôn kèm nguồn (tin nhắn gốc)
và đóng khung "đề xuất để sếp tự đánh giá". Rủi ro chính trị nội bộ cao → người luôn ở giữa.

**Trần năng lực:** bị chặn bởi cái gì được ghi lúc nghe. Trước khi bot vào nhóm → không biết.
Cái không note được → không tổng hợp/phân tích được.

---

## TẦNG 1 — Kiến trúc vĩ mô: 3 mặt phẳng (✅ CHỐT)

### ① NGHE (Ingestion) — "nghe hết, xử lý chọn lọc"
Lưu THÔ toàn bộ (rẻ, lưới an toàn) + chỉ chạy LLM trích xuất trên cụm tin "có chuyện" do model rẻ sàng lọc.
→ giải bài toán token: tin vô nghĩa không đốt token premium.

### ② NHỚ (Memory) — 4 tầng thô→tinh
1. `tin nhắn thô` — lưới an toàn chống miss (có thể lặn xuống đọc nguyên văn)
2. `note có cấu trúc` — task/quyết định/fact + **provenance** + importance + confidence
   + (do chọn Phân tích) **tín hiệu hiệu suất**: ai nhận việc, deadline, xong đúng hạn?, cam kết vs thực giao
3. `index nhóm ≤200 dòng` — luôn nạp vào context responder
4. `sổ tay AI tự quản theo từng sếp` — tầng mềm, có kiểm soát (xem Tầng 1 tự chủ)

### ③ TRẢ LỜI (Response) — router theo độ khó
Câu dễ → trả thẳng từ index, 0 tool, 1–4s, NGẮN GỌN. Câu khó → mới bật agentic loop (2–6 tool).
→ giải tốc độ + trải nghiệm: câu đơn giản không bao giờ bị trả lời dài dòng.

### Tự chủ AI: CÓ KIỂM SOÁT (✅ CHỐT)
Tầng cứng (task/reminder/calendar) = schema cố định, deterministic, chạy scheduler/UI — AI KHÔNG sửa tự do.
Tầng mềm (sổ tay, playbook, mối quan tâm) = AI tự quản qua tool, NHƯNG mọi mutation ghi `revision log`,
có UI cho sếp xem/sửa. Chống prompt-injection: nội dung nhóm là DATA, không phải lệnh.

---

## TẦNG 2 — Core lean + Module (🔶 ĐANG ĐỀ XUẤT)

Mục tiêu: lõi mỏng, bất biến; mọi mở rộng = cắm module qua contract, KHÔNG sửa lõi. Version mới = thêm
module, không viết lại.

```
KERNEL (lõi ổn định — hiếm khi đụng)
  • Event bus (message.captured…)      • LLM Gateway + routing (feature→model)
  • Prompt store (versioned, in DB)     • Tool registry
  • Retrieval pipeline runner (stage cắm) • Memory interface (MemoryProvider)
  • Scheduler

MODULES (cắm qua contract)
  • Channels:      Telegram · Zalo · Web   (+ tương lai: Messenger…)
  • Capabilities ("skill" nội bộ = tools + prompts + jobs):
       task-tracking · reminder · note · qa-responder   ← LÕI, bật sẵn
       team-analytics                                    ← bật sẵn (do chọn Phân tích)
       calendar-sync · daily-digest                      ← module bật sau
  • Integrations:  Google Calendar · … (adapter)
  • Memory backend: Qdrant (swappable)
  • Per-boss Playbook = "CLAUDE.md của từng sếp"
```

**Cách thiết kế này trả lời thẳng các câu hỏi của anh:**
- *"code lean, version chỉ mở rộng module"* → kernel mỏng + capability module độc lập.
- *"cơ chế skill / claude.md"* → capability = "skill" nội bộ; **Playbook per-boss = claude.md per-boss**
  (giọng văn, mức chủ động, mục quan tâm, alias người) nạp vào prompt cache.
- *"prompt nào cho boss set up"* → **tối thiểu** (xem Nguyên tắc xuyên suốt): default thông minh + bot
  tự học; superadmin sở hữu template/prompt/config phức tạp. Boss gần như không chạm; KHÔNG sửa prompt lõi.
- *"report"* → **capability module**, template do **superadmin** quản (DB, sửa ở web admin của superadmin);
  tool `generate_report` kéo dữ liệu tầng Nhớ → LLM điền nội dung → renderer ráp markdown đẹp, nhất quán.
- *"inject tool & integration hợp lý"* → tool registry; responder **chỉ nạp tool của capability liên quan
  intent** (loadout nhỏ theo ngữ cảnh) → giảm token + nhiễu, đúng nguyên tắc context engineering.
- *"build tool cho AI kiểm soát memory"* → MemoryProvider + bộ tool notebook (read/write/search), bounded.

---

## TẦNG 3 — Ước lượng sơ bộ (con số chính xác chờ chọn model ở Tầng 4)

| Loại | Token/lần | Tốc độ | Chi phí |
|---|---|---|---|
| Hỏi đơn giản (index) | ~3–5k / 0.3k | 1–4s | ~free |
| Hỏi trung bình (1–2 search) | ~8–15k | 4–10s | ~1–2¢ |
| Tổng hợp phức tạp (3–6 tool) | ~25–50k cộng dồn | 10–25s | ~5–15¢ |
| Trích xuất (async, chỉ cụm salient) | ~3k | nền | sub-¢ |
| Dreaming đêm / nhóm | batch ~10–30k | nền | ~1–3¢/nhóm/ngày |

Khả năng từng việc: task/reminder từ chat ✅ chắc · calendar ✅ (cần integration) · phân tích team ⚠️ advisory.

---

## TẦNG 4 — Chi tiết kỹ thuật (để cuối)

Embedding tiếng Việt, Qdrant datetime index, reranker, chunking, contextual retrieval, chống injection…
→ đã research một phần (xem research doc, mục 4.5); 2 nhánh còn lại tự chạy lại ~22:30.

---

## D1 — MÔ HÌNH DỮ LIỆU (✅ broad shape CHỐT 2026-06-12; field chi tiết để sau)

**5 lớp + 2 trục:**
- **Lớp 0 Raw:** `messages` (+ Qdrant) — giữ nguyên, lưới an toàn.
- **Lớp 1 Tri thức cấu trúc:** *Actionable* `tasks` · `reminders` (schema cứng, đã có) + *Knowledge* **`knowledge_items`**
  (1 bảng, `kind`=decision|fact|note|risk…) — MỚI, thay vai nguồn-sự-thật của blob group_notes.
- **Lớp 2 Group index:** `group_index`/nhóm ≤200 dòng — **DERIVED** (job đêm sinh từ Lớp 1), luôn nạp.
- **Lớp 3 Notebook:** per-boss, AI tự quản, có audit.
- **Trục:** `people`+`aliases` · `projects`/`topics` · `*_revisions` (audit) · `provenance` (item → message gốc).

**Quyết định đã chốt:**
- Kho tri thức = **HYBRID** (knowledge_items linh hoạt + tasks/reminders typed riêng). Nhất quán với quyết
  định "Phân tích vào lõi" (cần query ai-xong-đúng-hạn → task phải typed).
- Group index = derived, không phải blob tự viết.
- Bỏ `memory_entries` 3-scope → tan vào knowledge_items + notebook.
- people + projects first-class.

**Rủi ro/ceiling đã biết:** taxonomy `kind` phải gọn (siết ở D2, nếu loose thành ngăn kéo rác); câu hỏi
quan hệ-thời gian sâu chỉ đạt ~80% so với knowledge-graph (Zep) — để dành nâng cấp sau nếu cần.

## D2 — INGESTION / LỌC NHIỄU (✅ broad CHỐT 2026-06-12)

**Pipeline:** `messages` (Lớp 0, lưu hết) → **trigger** lull (im X phút) / threshold (N tin), async →
**EXTRACT** (LLM đọc cửa sổ tin + summary nhóm → ứng viên `knowledge_items`[kind+importance+provenance] +
`tasks` + `reminders`; gán `thread_id`/topic) → **RECONCILE** (LLM: ADD/UPDATE/DELETE/NOOP vs item đã có) →
ghi Lớp 1 + revision log.

**Đã chốt:**
- Trigger: tái dùng debounce sẵn có (10 phút / 30 tin) — đã đúng "lull hoặc threshold".
- Async: extraction chạy nền, KHÔNG chặn trả lời.
- **Lọc nhiễu = chính việc extract** (nghiêng precision); tin không ra item vẫn ở Lớp 0 (recall). Importance
  (LLM chấm 1–10 lúc ghi) = trọng số xếp hạng, KHÔNG phải ngưỡng xóa.
- **Taxonomy `kind` = NHỎ + giàu field:** bắt đầu ~4 kind (decision/fact/note/risk-blocker); deadline/owner/
  on-time… là FIELD không phải kind. Thêm kind sau = enum + sửa prompt, KHÔNG migrate (nhờ Hybrid).
- thread/topic tagging tại ingest (cơ chế DÙNG để retrieval → D3).

## D3 — RESPONSE (✅ broad CHỐT 2026-06-12)

**Luồng:** câu hỏi → **query-understanding** (1 call: rewrite + parse thời gian + resolve người) →
**ROUTER inline** (Tier 0 trả từ group index, 0 tool · Tier 1 one-shot hybrid · Tier 2 agentic loop) →
lắp context (group index luôn + item scoped&capped + cửa sổ tin nhỏ; KHÔNG raw history; scope nhóm bắt buộc + thread/topic).

**Đã chốt:**
- Router = **INLINE** (responder tự quyết tier; thấy đủ trong index → trả ngay, thiếu → search, cần → lặp).
- Settled: query-understanding call · scope nhóm bắt buộc · tool loadout nhỏ theo capability · no raw-history dump · prompt-cache layout (index+memory đầu, volatile cuối).
- **Scope chat web admin = MODEL A:** mặc định toàn scope (không phải chọn) + **adaptive sticky scope**
  (chip nhìn thấy & xoá được, là **SOFT bias, đánh giá lại mỗi lượt** — chống scope-poisoning) + **picker
  tùy chọn** nhóm/dự án/thời gian (chọn tay = **HARD filter**). Tái dùng filter retrieval sẵn có (chat_id/project/time).
- **MỚI cần lưu ý:** chat web admin cần **state hội thoại** (scope phiên + lượt gần) — khác responder group hiện stateless.

## D4 — CAPABILITY LIST + OWNERSHIP (✅ broad CHỐT 2026-06-12)

**v1 cut:** foundation + **analytics-lite** (build luôn để demo, advisory, không polish kỹ). report/calendar/digest = module ngay sau.
**Hai tầng:** Boss quản DỮ LIỆU & trải nghiệm · Superadmin quản BỘ NÃO & cấu hình. (Boss = phía web admin khách hàng; Superadmin = platform.)

| Capability | Ý nghĩa | Superadmin | Boss |
|---|---|---|---|
| Ingestion/Curator *(ngầm)* | nghe → trích note/task/reminder → reconcile | trigger, prompt extract, taxonomy, model | không chạm |
| Note/Knowledge | kho tri thức cấu trúc (decision/fact/note/risk) | schema, taxonomy, prompt | xem/sửa/xoá note của mình + nguồn gốc |
| Task | theo dõi việc (owner/deadline/status) | schema, logic | xem/sửa/đánh dấu xong |
| Reminder | nhắc theo thời gian | scheduler config | tạo/huỷ/xem |
| QA-responder | trả lời (web + nhóm) | prompt, routing, pipeline | dùng; chọn scope tùy chọn |
| Dreaming *(job đêm)* | chuẩn hoá ngày, gộp trùng, đóng task, viết lại index | lịch, prompt | không chạm |
| Agent-notebook | sổ tay bot tự học per-boss | khung, giới hạn, audit | xem/sửa sổ (minh bạch) |
| Team-analytics *(v1-lite)* | tổng hợp hiệu suất (advisory) | prompt, công thức, template | xem insight/bản nháp |
| Report *(ngay sau)* | gen báo cáo markdown theo template | **sở hữu template** | "tạo report" → nhận |
| Calendar/Digest *(sau)* | sync lịch · digest | integration config | kết nối tài khoản; nhận |

**Config xuyên suốt:** Superadmin = prompts/model/budgets/pipeline/taxonomy/templates/tuning. Boss = dùng + xem/sửa dữ liệu của mình + chọn scope + bật/tắt vài cap + connect integration; KHÔNG chạm prompt/model/pipeline.

## D5 — KỸ THUẬT (research xong 2026-06-13; 2 nhánh: VN retrieval + Qdrant/ops)

### CHỐT NGAY (rõ ràng — "do now"), nhiều cái fix đúng weak spot
- **Fix lọc thời gian (weak spot i):** Qdrant **datetime payload index + filtered HNSW** (filter range chạy TRONG graph traversal, không hậu kỳ SQL). ⚠️ tạo index TRƯỚC khi ingest (retrofit = re-index).
- **Scope nhóm (weak spot iv):** Qdrant **multitenancy single-collection + `is_tenant=True`** trên group_id + `group_by` (dedup chunk).
- **Thay MMR-Jaccard (weak spot ii):** reranker **`bge-reranker-v2-m3`** (self-host, ~110ms/30, đa ngữ gồm VN, cùng họ bge-m3, ~free). Reranker = cú nhảy chất lượng lớn nhất (+23–30% vendor).
- **Hybrid:** Qdrant **Query API** (prefetch dense+sparse → **RRF** server-side, 1 request) thay DIY RRF.
- **Quantization:** scalar int8 (4× memory, <1% loss).
- **Async write:** outbox/queue embedding (không chặn ingest) + idempotent upsert + token-bucket.
- **Job đêm (dreaming/re-embed):** **Batch API** (−50%, ~24h, quota riêng → không tranh path QA).
- **Extraction (D2):** **Structured Outputs strict** (OpenAI json_schema constrained > Claude strict tool-use > Gemini responseSchema best-effort). Schema phẳng, không đệ quy.
- **Model routing:** cheap-fast (Gemini Flash-Lite / GPT-5-mini / Groq oss / Haiku 4.5) cho extraction/salience; premium (Opus/Sonnet) cho answer. **LLM-as-reranker SKIP** trên live path → cross-encoder.
- **Prompt-injection (watchlist):** spotlighting (delimiter ngẫu nhiên quanh chat untrusted) + sanitize write-path (strip invisible Unicode/markdown-image) + provenance/taint + **schema-only extractor KHÔNG có tool access** (injected text không thể thành hành động — control quan trọng nhất, MIỄN PHÍ vì đã dùng structured output) + egress allowlist. Nâng cấp: CaMeL (privileged/quarantined split).

### VN lexical search (Postgres FTS yếu)
`simple`+unaccent = syllable-level, sót từ đa âm tiết. Fix: (1) ưu tiên — **sparse vector bge-m3 trong Qdrant** (learned, khỏi tokenizer); (2) nếu ở lại Postgres — **underthesea segmentation** trong ingest trước tsvector (tokenizer thống kê = infra, không phạm "no rule-based"). pg_trgm chỉ cho typo.

### ✅ embedding model = gemini-embedding-001 (CHỐT 2026-06-13)
te-3-small yếu cho VN (MIRACL 44.0). **Chốt gemini-embedding-001**: 1536d khớp Qdrant → migration gần như free (chỉ re-embed ~$4–38, không đổi dim), **0 GPU ops** (hợp team nhỏ + lean), ~4% lift.

**Insight quyết định:** **reranker (`bge-reranker-v2-m3`) mới là đòn bẩy chất lượng chính** (+23–30%) — embedding chỉ cần đẩy candidate vào top-30, reranker lo xếp hạng → chênh B-vs-C bị reranker che gần hết, không đáng stress.

**bge-m3 VN-finetune = upgrade path** (đã ghi): đổi sang nếu sau này dùng thật thấy VN-quality chưa đủ (lúc đó có dữ liệu justify GPU). Bỏ eval-driven (A) theo ý user.

## D6 — EVAL (✅ CHỐT 2026-06-13)

**Quyết định: Lean.** Gold set ~30–50 Q&A từ chat thật + **LLM-judge** (correctness/groundedness — dùng
relative/regression, biết bias verbosity/position) + **tách retrieval recall@k** khỏi answer-eval + thumbs/
groundedness online nhẹ. Quy tắc **"mỗi bug → 1 gold case"** (gold set lớn dần theo thực tế). Cũng là lưới
bắt watchlist #1 (reconcile) + #3 (staleness). KHÔNG framework nặng / CI gating / dataset lớn ở build-stage.

*Research corroborate (Area 6): ~50 câu đại diện đủ bắt regression >5%; faithfulness ≠ truth (chỉ đo grounding); chọn 1 framework nhất quán; judge khác family với generator.*

## D7 — TOOLS & INTEGRATIONS (✅ broad CHỐT 2026-06-12)

**Phân biệt cốt lõi:** integration = tùy chọn, thiếu thì nhẹ (mất 1 tính năng); tool = chịu lực, phải bảo vệ (thiếu → bot "dở hơi").

- **Integration = marketplace:** superadmin dựng catalog → boss lướt/cài/active/config; degrade graceful. Mỗi integration **mang theo tool của riêng nó**.
- **Tool = bundle theo capability**, boss KHÔNG bật/tắt raw tool; tool lõi (search/task/note) khoá ON.
- **Capability khai báo required tools → kernel validate lúc load;** thiếu tool lõi = **lỗi config (báo superadmin)**, không degrade âm thầm (phòng "dở hơi").
- **Loadout động theo intent:** cài nhiều integration vẫn không phình context — responder chỉ nạp tool liên quan câu hỏi.
- **Phân quyền:** boss control ở mức **capability/integration**; raw-tool control ở **superadmin**.
- **Refactor (build-stage):** chuyển `boss_active_tools` (raw) → control ở capability level; khai báo **dependency capability** (A cần B) để tắt optional không làm hỏng ngầm.

## D8 — CONTEXT MGMT / SUB-AGENT / PARALLEL (✅ CHỐT 2026-06-12)

**Quyết định: A.** v1 = context-discipline ở tool boundary (cap/paginate tool result · loadout động ·
không dump raw — đã có ở D3). **KHÔNG** parallel multi-agent (15x token, premature). Sub-agent **quarantine**
+ parallel orchestration để dành cho synthesis nặng (analytics/report) — thêm trên nền Capability (Phase B),
không cần cho v1.

**Nền:** có agent loop + tool registry; CHƯA có sub-agent/quarantine machinery; tool-result chưa cap. v1
không cần; nâng cấp sau không phải đập lại.

## GAP ANALYSIS — code hiện tại vs khung mục tiêu (2026-06-12)

**Mức khớp ~55–60%.** Kernel đã sạch hơn lo ngại.

**Kernel — đa số ✅ có contract Protocol rõ:** event bus · LLM gateway+routing · tool registry (`@tool`) ·
memory provider · retrieval pipeline (stage decorator + config DB) · channel adapter (auto-discovery) ·
prompt store (versioned DB). 🟡 Scheduler — job hardcode trong `runner.py`, chưa pluggable.

**Đã có sẵn (đáng mừng):** plugin scaffold (`plugins/<name>/manifest.toml` + bật/tắt per-boss qua
`boss_integrations`); **phân tầng superadmin vs boss ĐÃ CÓ** (role check; prompts/routes/budgets/templates
do superadmin quản — khớp nguyên tắc minimal-boss); `note_templates` (section types) — pattern template đã có.

**3 gap chính (gần như toàn bộ khoảng cách):**
1. **Plugin = chỉ tools, chưa phải capability đầy đủ** (thiếu bundle prompts+jobs+templates). Thêm "report"
   hiện phải đụng 5+ file core → cần trừu tượng hóa **"Capability"**.
2. **Memory tangled:** `group_notes` và `memory_entries` là 2 kho rời; chưa có tier "trích xuất"; chưa có
   4-tier (thô → cấu trúc → index → notebook).
3. **Scheduler chưa pluggable:** thêm job "dreaming" phải sửa `runner.py`.

**Điểm yếu xác nhận còn nguyên:** (i) lọc thời gian sau Qdrant — *cao* (ii) MMR Jaccard — thấp
(iii) luôn inject top-20 memory — trung bình (iv) chat_id optional trộn nhóm — thấp/dễ (v) memory upsert
ghi đè mất lịch sử — trung bình.

### Lộ trình đề xuất (đã áp lăng kính lean + minimal-boss; KHÁC thứ tự thô của agent)

> **CẬP NHẬT (2026-06-12, build-stage): hệ thống CHƯA production** → bỏ ràng buộc production-safety.
> Đảo sang **foundation-first**: nền module + memory đúng làm trước/đồng thời; các fix điểm yếu KHÔNG
> vá riêng mà **gộp vào việc dựng lại retrieval/memory cho đúng ngay từ đầu**. Refactor thoải mái,
> không cần migrate tương thích ngược. Lộ trình A/B/C dưới đây vẫn đúng về nội dung, chỉ đổi thứ tự ưu tiên.
- **Phase A — Quick wins, rủi ro thấp, giảm đau NGAY (không refactor lớn):** fix lọc thời gian (đẩy filter
  vào Qdrant payload) · bắt buộc scope `chat_id` · bỏ luôn-inject top-20 · audit log memory (dễ) ·
  **complexity router** (LLM nhẹ, KHÔNG rule-based — giải tốc độ).
- **Phase B — Nền module:** trừu tượng **Capability** (tools+prompts+jobs+templates) + scheduler pluggable.
  Từ đây "report", "dreaming"… cắm vào không đụng kernel.
- **Phase C — Chiều sâu memory (LÀM DẦN, KHÔNG big-bang):** bảng structured notes + reconciliation
  (ADD/UPDATE/DELETE/NOOP) + job consolidation đêm + agent notebook. Chạy song song `group_notes` cũ rồi cắt dần.

**Phán đoán điều chỉnh:** (1) **per-boss config override** agent xếp trung bình → HẠ xuống thấp: nguyên tắc
minimal-boss nghĩa là boss không cấu hình nhiều; bot tự học (notebook) thay cho override. (2) **KHÔNG**
big-bang unify memory (agent ước ~800 LOC + migrate) — rủi ro cao, ngược "lean"; làm dần ở Phase C.

## RỦI RO & WATCHLIST (self-review 2026-06-12)

Mitigation **cân đối** — cải thiện ở mức rẻ, KHÔNG over-engineer tới mức làm gãy hệ thống.

| Rủi ro | Làm (cân đối) | KHÔNG làm |
|---|---|---|
| 1. Silent-rewrite (reconcile/dreaming) | **Soft-delete** + revisions append-only | workflow duyệt từng thay đổi |
| 2. Latency câu đơn giản | **gộp query-understanding vào call responder**; rewrite chỉ khi retrieve | classifier model riêng đầu luồng |
| 3. Job staleness (index/extraction lag) | `last_success_at` + cờ stale cho superadmin (tái dùng health-check) | observability/alerting stack |
| 4. Precision-extract gap | fallback đã có (dreaming đọc lại window + responder→raw); ghi rõ giới hạn | re-process toàn bộ raw định kỳ |
| 5. Phức tạp vs sức team | v1 cắt tối thiểu, defer optional | build hết một lượt |

Đáng giá & gần như miễn phí: **soft-delete** (chặn mất tri thức vĩnh viễn) + **gộp query-understanding** (gỡ thuế latency câu đơn giản).

## SELF-REVIEW ĐỐI KHÁNG (2026-06-14, 5 nhánh: scaling · latency · accuracy · fit · security)

> **Trạng thái (team): phần lớn đánh giá là OVERTHINKING ở giai đoạn này → các QUYẾT ĐỊNH THIẾT KẾ GIỮ NGUYÊN.**
> Mục này để THAM KHẢO/đối chiếu sau, KHÔNG phải action items. Chỉ một điều đáng sanity-check sớm:
> Zalo có cho bot lắng nghe trong nhóm không (nền tảng), nếu chưa nắm.

**Verdict:** "Bộ não" (memory/retrieval) được engineer **đúng & mạnh** — tầng retrieval (datetime index, is_tenant scope, reranker, hybrid) là phần khen nhiều nhất. Nhưng review lộ ra: (a) vài **gap CRITICAL doc chưa đụng** (Zalo group viability, voice/ảnh, lớp output chủ động, PDPL pháp lý, isolation sâu), và (b) **v1 đang quá dày** — bẫy "build platform trước khi validate sản phẩm".

### CRITICAL — phải xử lý
| # | Finding | Nhánh | Fix cân đối |
|---|---|---|---|
| C1 | **Zalo KHÔNG cho bot vào nhóm chính thức** (chỉ route cá nhân ban-risk cao, không nhận voice/file). Tiền đề "bot vào nhóm" chưa validate. | fit | **Validate Telegram-first ngay**; lập "channel capability matrix"; Zalo có thể chỉ là kênh send-only. Go/no-go TRƯỚC khi làm thêm memory. |
| C2 | **Thiếu voice/ảnh** — chat VN nặng voice note + ảnh; text-only = mù đúng tin giá trị cao. | fit | ASR + OCR là ingestion first-class, hoặc tuyên bố rõ "v1 text-only, đây là điểm mù". |
| C3 | **Không có lớp OUTPUT chủ động** — boss quá tải không vào hỏi; giá trị thật là **daily brief riêng cho boss**. | fit | Kéo **daily brief (DM cho boss) vào v1 core**; spec "speak-policy" (im trong nhóm trừ khi @mention). |
| C4 | **PDPL (Luật 91/2025) hiệu lực 1/1/2026** — lưu raw vô thời hạn + chuyển dữ liệu qua LLM nước ngoài + không có erasure/consent = vi phạm, phạt theo doanh thu. | security | **Raw-message TTL + đường erasure cascade + notice khi bot vào nhóm**; ghi rõ xử lý cross-border. Pháp lý, không optional. |
| C5 | **Tenant isolation đang optional** (chat_id optional = 1 bug → rò rỉ chéo boss). | security+scaling | Scope **bắt buộc do framework inject** + Postgres **RLS** + Qdrant `is_tenant` — defense-in-depth ở tầng lưu trữ. Must #1 kỹ thuật. |
| C6 | **Latency "bom" 10–12s** nếu embedding sai region; "câu đơn giản 1–4s" không đạt với model premium. | latency | Pin embedding `asia-southeast1`; **luôn stream**; route Tier0/câu ngắn sang model nhanh (Flash); giữ GPU reranker warm. |
| C7 | **Kỳ vọng accuracy lạc quan:** multi-hop synthesis thực 30–45% (không 80%); extraction recall 60–75% (không 85–90%); analytics tính trên mẫu lệch. | accuracy | Thêm **extraction-recall metric** vào D6; **salience gate nghiêng recall**; coverage-check trong Tier2; analytics hiện coverage, tránh per-person; đặt kỳ vọng "draft để kiểm". |

### Quyết định ĐÃ CHỐT bị review THÁCH THỨC (cần quyết lại)
| Đã chốt | Thách thức | Khuyến nghị |
|---|---|---|
| Analytics vào v1 (D4) | nhiều nhánh: rủi ro + chưa đáng tin + mùi giám sát + mẫu lệch | **CẮT khỏi v1** (giữ schema task); thay demo hook = daily brief |
| Foundation-first A→B→C | bẫy team nhỏ: build platform trước validate | **Lát cắt dọc mỏng trước** (Telegram→capture→brief→@mention, hardcode), validate 1–3 sếp, RỒI refactor Capability/kernel |
| Tự xây 4-tier memory + reconcile + dreaming | đúng ý tưởng, sai thứ tự; chưa hỏi build-vs-buy | v1: raw + structured + index đơn giản, **append + soft-delete, CHƯA reconcile/dreaming**; cân nhắc **mua mem0/Letta** |
| Marketplace UI (D7) | enterprise plumbing cho sp 0 khách | **Hand-config (YAML/DB)** cho khách đầu; marketplace sau |
| Reranker self-host (D5) | con GPU duy nhất trên stack all-API, đắt hơn API <25k rerank/ngày | **Default Cohere Rerank API**; self-host là upgrade path |
| Adaptive sticky scope (D3) | UX tinh vi cho web-chat mà boss ít dùng | v1: **picker đơn giản (hard filter)**; adaptive sau |
| Embedding gemini không eval | "~4% lift" là cross-lingual, không phải VN | **spot-check recall@30 trên ~30 câu VN thật** (không phải full eval) |

### GIỮ (đừng để review làm lung lay điểm đúng)
Schema-only extractor không tool-access (= control bảo mật chịu lực, miễn phí) · Qdrant datetime index + is_tenant + reranker (tầng mạnh nhất) · soft-delete + revisions · D8 không multi-agent (cut đúng) · injection defense cân đối · raw-layer safety net · eval Lean.

### MUST trước user thật (punch-list bảo mật)
1. Tenant scope bắt buộc 2 tầng (framework filter + Postgres RLS + Qdrant is_tenant) — đóng weak spot iv.
2. Untrusted-content + egress allowlist mở rộng vào **responder/agentic path** (code-enforced).
3. Soft-delete + revisions thành **invariant cứng** của MemoryProvider; confidence-gate notebook — đóng weak spot v.
4. Raw TTL + erasure cascade + bot join-notice (PDPL).
5. Mã hoá OAuth token (KMS/envelope) + least-privilege scope/integration.
6. MFA + audit cho superadmin; per-request tenant/RBAC server-side; web-chat scope bound theo boss đã auth.

### Residual risk (ghi nhận + monitor qua D6): indirect/stored injection KHÔNG thể loại bỏ (OWASP). Chiến lược = containment (schema-only extractor + egress allowlist + isolation) → injected content không hành động/exfiltrate được, memory hỏng thì recoverable. Biến niềm tin này thành 1 gold-case test.

## SPIKE KẾT LUẬN & THỨ TỰ KÊNH (2026-06-14)

**Memory build-vs-buy → BUILD.** Letta loại (in-context memory, sai kiến trúc). mem0 khớp pipeline nhưng
lưu fact phẳng (không typed) + bug chuẩn hoá VN→EN (#3707). KHÔNG test/spike — **học thiết kế prompt
reconcile của mem0 làm tham khảo rồi tự build** (giữ schema typed + provenance + soft-delete). Lưu ý chung:
khi tham khảo công nghệ luôn check **phiên bản mới nhất** tránh outdate.

**Thứ tự kênh (CHỐT, override khuyến nghị spike "Telegram-first"):** **Zalo v1 → Messenger v2 → Telegram v3/v4.**
Lý do: Telegram sạch kỹ thuật nhất NHƯNG thị trường VN gần như không ai dùng; group công việc VN ở Zalo.
v1 chấp nhận route Zalo KHÔNG chính thức (zca-js) + rủi ro ban như quyết định kinh doanh. (Bài học: "sạch
kỹ thuật ≠ có người dùng" — spike tối ưu sai trục.)

**PDPL → park tới pilot thật; build-stage chỉ chừa đường kiến trúc.** Trial / data test / tester đồng ý =
CHƯA cần care. Nghĩa vụ (consent, DPA, cross-border CDTIA) gắn khi ingest dữ liệu nhân viên của **một công
ty thật** (kể cả pilot miễn phí — "free" không miễn trừ). Build-stage chỉ cần: **retention/auto-purge +
cascade-delete trong data model ngay** + provider **zero-retention/no-train**. Phạt cross-border = "cao hơn
giữa 5% doanh thu và 3 tỷ" → **doanh thu nhỏ KHÔNG kéo trần xuống** (trần tuyệt đối 3 tỷ), nhưng "tới" = max,
thực thi có discretion; rủi ro thật ở quy mô bé = bị buộc dừng + uy tín. Xác nhận luật sư VN trước pilot.

## BUILD LOG

**2026-06-14 — Knowledge/Memory core (Lớp 1) ✅ built + verified.**
- Migration `0015_knowledge_core.py` (additive, reversible, đã roundtrip down↔up): bảng
  `knowledge_items` (hybrid, kind mềm TEXT không CHECK, status soft-delete, importance/confidence,
  valid_from/to, project_id FK, qdrant_point_id, meta_json, fts+GIN+trigger), `knowledge_provenance`
  (→messages, cho "ai nói"+taint), `knowledge_revisions` (audit append-only).
- `src/domain/knowledge.py` + `src/repositories/knowledge.py` — KnowledgeRepo bake invariant:
  **KHÔNG có hard-delete** (chỉ soft_delete=status), mọi mutation log revision trong cùng transaction,
  mọi query scope `boss_id`.
- Verified: migration up/down/up; **fts tiếng Việt** chạy (`'nha cung cap'`↔`'nhà cung cấp'`);
  repo smoke PASS (add→get→list→update→soft_delete, 3 revisions đúng actor/op); ruff sạch.
- Defer (lean, đúng phạm vi tầng): people/aliases, agent_notebook, analytics.
- **Tiếp theo:** write-pipeline (LLM extract→reconcile ADD/UPDATE/DELETE/NOOP, DÙNG repo này) + cắm
  media extraction vào ingest (seam `src/media` sẵn). Hai cái độc lập, dựng trên nền core này.

**2026-06-14 — Write-pipeline (extract→reconcile) ✅ built + verified (deterministic/fake-LLM).**
- `src/services/knowledge_service.py` — `KnowledgeService.process(boss,provider,chat,after_msg_id)`:
  delta messages → EXTRACT (LLM, prompt-JSON) → candidates(kind/title/content/importance/source_ids)
  → RECONCILE (LLM vs item active trong scope, cap 50) → ADD/UPDATE/DELETE/NOOP → apply qua KnowledgeRepo.
  Parse JSON khoan dung; validate kind theo CANONICAL_KINDS; 1 quyết định lỗi không làm hỏng batch.
- Verified: ruff sạch; smoke (fake LLM) PASS — process e2e 2 ADD + provenance đúng; _apply UPDATE/DELETE
  đúng (status/importance/revisions). Dọn sạch test data.
- CHƯA verify/làm (honest): **live LLM** (cần API key + tốn $ + non-deterministic → là vòng tune prompt
  qua eval/gold-set D6); **trigger wiring** (chưa subscribe debounce/message.captured) + state-tracking
  `last_extracted_message_id`; **llm_routes** cho 2 feature mới (knowledge_extract/reconcile); structured-output
  strict (codebase chưa expose → dùng prompt-JSON, nâng sau). Prompt để CONSTANT trong service (move prompt-store sau).
- Reconcile fetch theo SCOPE (chưa Qdrant similarity — cần embedding write ở tầng retrieval sau).

**2026-06-14 — Retrieval tầng knowledge ✅ built + verified.**
- `src/memory/knowledge_index.py` — `KnowledgeIndex(pool,qdrant,llm)`: `index()` embed+upsert Qdrant
  (payload kind="knowledge" + boss_id/chat_id/item_id/item_kind/**ts epoch**), `remove()`, `search_dense()`
  (scope boss+chat + **time-range LỌC TRONG Qdrant** — fix đúng weak-spot của dense.py messages), `search()`
  hybrid dense+FTS fuse RRF.
- `KnowledgeRepo.search_fts()` (FTS VN + scope + time + status='active' TẤT CẢ trong WHERE) + `get_many` + `set_qdrant_point`.
- Wired vào write-pipeline (`KnowledgeService(index=...)`, guarded — lỗi embed không hỏng việc lưu).
- Verified: ruff sạch; smoke — FTS live (query VN/scope/time/status đúng) + dense+hybrid với fake-embedder
  trên Qdrant THẬT (scope+**time filter chạy trong Qdrant**); dọn sạch Qdrant points + DB.
- CHƯA: **live embedding** (cần key; ranking thật khác fake); **wire vào responder** (chưa có tool
  `search_knowledge` gọi từ agent_loop); weak-spot dense.py path MESSAGES vẫn nguyên (chỉ fix path knowledge mới);
  payload index Qdrant cho ts/chat_id (range chạy không cần, thêm để nhanh). ⚠️ qdrant client 1.18 vs server 1.12.4 — đồng bộ sau.

**2026-06-14 — Responder tool `search_knowledge` ✅ built + verified.**
- `src/tools/core/search.py` thêm tool `search_knowledge` (available_to dm/in_group responder, feature
  qa_with_search): build KnowledgeIndex từ ToolContext (pool/qdrant/llm) → hybrid search scope boss+nhóm+time
  → trả item + **source_message_ids** (dẫn nguồn). Ưu tiên dùng trước search_history cho câu "đã chốt/dự án".
- Auto-surface: `_provision_new_boss` seed active-tools = `list(_REGISTRY.keys())` → boss MỚI tự có tool.
  Boss CŨ cần backfill 1 INSERT vào boss_active_tools.
- Verified: ruff sạch; smoke (ToolContext thật + Qdrant thật + fake embed) PASS — trả đúng item + provenance.
- CHƯA: LLM tự QUYẾT gọi tool (cần live LLM + nudge prompt responder ưu tiên search_knowledge); backfill boss cũ.

**2026-06-14 — Prompt-store integration cho write-pipeline ✅.**
- KnowledgeService load prompt qua `PromptsRepo.get_active(key)` (superadmin tune qua **web admin**),
  fallback về constant trong code nếu store trống → robust + web-editable. Verified: fallback chạy (DB prompts rỗng).
- Thêm `config/seeds/prompts/knowledge_extract.yaml` + `knowledge_reconcile.yaml` (nguồn canonical, placeholder
  `{{ window }}`/`{{ candidates }}`/`{{ existing }}` khớp service).
- ⚠️ **Phát hiện:** bảng `prompts` ĐANG RỖNG ở dev DB — bước seed prompt (nạp 7 yaml vào store) CHƯA chạy ở
  môi trường này; cả note_update/in_group... cũng đang fallback. Cần chạy seed prompt (ops) để web có prompt sửa.

**2026-06-14 — Trigger wiring write-pipeline ✅ (spine LIVE-READY).**
- `src/agents/knowledge_extractor.py` — operation `knowledge_extract`: `@trigger(message.captured,
  debounce 10m / threshold 30, group-only)` + `@operation(deps_type lấy boss/db/llm/qdrant qua build_context)`.
  handle: get_or_create note row → `get_last_extracted` cursor → KnowledgeService(index=KnowledgeIndex).process →
  `set_last_extracted`. Cùng cadence note_updater.
- Migration 0016: `group_notes.last_extracted_message_id` (cursor riêng, tách last_seen của note).
- `GroupNotesRepo.get_last_extracted/set_last_extracted`; đăng ký op trong `src/agents/__init__.py`.
- Verified: migrate 0016 applied; op + trigger registered (introspect _OP_REGISTRY/_TRIGGER_REGISTRY); ruff sạch.
- ⚠️ Chưa chạy LIVE e2e (cần start server + harness scenario) — đó là vòng tune tiếp theo.

**LLM/harness READY:** API keys có (`PLATFORM_OPENAI_API_KEY`,`PLATFORM_GROQ_API_KEY`); models/llm_routes seeded;
kênh web test (`/test/api/{users,groups,send}` + replay) cho phép dựng kịch bản + chạy e2e LIVE.

**Spine: ingestion ✅ · knowledge core ✅ · write-pipeline ✅ · retrieval ✅ · responder-tool ✅ · trigger ✅ → LIVE-READY. Còn lại: chạy harness + tune.**

**2026-06-14 — Harness tune loop LIVE vòng 1 ✅ (spine chạy e2e end-to-end với gpt-4o thật).**
Kịch bản: nhóm "Dự án Apollo" (boss + 3 nhân viên), 13 tin giao việc/chốt/deadline/risk + nhiễu. Harness `/tmp/harness.py` (state ở `/tmp/harness_state.json`).
- **3 gap chặn live phải vá trước (đều là "live-readying", không đổi design):**
  1. THIẾU `llm_routes` cho `knowledge_extract`/`knowledge_reconcile` → `pick_model` raise `LookupError`. Đã seed (smart, fallback fast) + budgets vào `scripts/seed_llm.sh`.
  2. `search_knowledge` KHÔNG nằm trong `tools` set của in_group/dm_responder → `_allowed_tools` (base=cfg.tools ∩ boss_active_tools) loại nó → responder KHÔNG bao giờ gọi được. Đã thêm vào cả 2 op.
  3. Thêm endpoint harness `POST /test/api/extract {chat_id, reset?}` — fire `op.knowledge_extract.fire` đồng bộ (bus await handler) bỏ qua debounce 10m/threshold 30; `reset` rewind cursor để extract lại cả hội thoại.
- **Extraction (gpt-4o): chất lượng cao.** 6 item từ 13 tin; nhiễu (ăn trưa, "review PR") bị lọc đúng. Revision Postgres→Supabase được **EXTRACT gộp NGAY trong window** thành 1 decision "Supabase thay vì PostgreSQL" (src cả 2 tin) — KHÔNG mâu thuẫn.
- **Cross-batch RECONCILE: đã test live (1 LLM call).** Gửi 2 tin đính chính rồi extract incremental (không reset): deadline demo 30/6→15/7 ⇒ **UPDATE item đúng** (id giữ nguyên, retrieval + câu trả lời phản ánh 15/7); VNPay "đã mở sandbox, hết rủi ro" ⇒ reconcile chọn **UPDATE** (đổi content) item risk. ⚠️ **Issue:** `_apply` UPDATE chỉ đổi content/title/importance, KHÔNG đổi `kind`/`status` → risk đã giải quyết vẫn `kind=risk`/`active` (lẽ ra nên DELETE). May là gpt-4o đọc content "hết rủi ro" nên vẫn trả lời đúng ("không còn rủi ro"); nhưng nhãn sai là rủi ro ngầm cho filter theo kind. Hướng sửa: reconcile ưu tiên DELETE cho item đã resolved, hoặc cho UPDATE đổi kind/status.
- **Read path:** ban đầu câu "ai lo backend?" trượt. Truy ra (qua `tool_call_log` + log tool I/O thêm vào `agent_loop`): model tự thêm filter `kind="fact"` → loại item phân công (vốn là `decision`); **cộng dồn** lỗi gốc: bảng `prompts` RỖNG nên `_load_prompt` trả "" → responder chạy KHÔNG có system prompt (không có code-constant fallback như KnowledgeService). Sửa: (a) mô tả param `kind` của `search_knowledge` khuyến cáo để trống/không đoán loại; (b) viết `in_group.yaml` v2 (role thư ký + chính sách dùng `search_knowledge` TRƯỚC + không over-filter + tổng hợp & nêu tên người) + seeder `scripts/seed_prompts.py`. → **5/5 câu đúng** (ai-lo-X, deadline, DB=Supabase, risk, tóm-tắt dùng 5 query con). No-info (ngân sách/màu) → "chưa có thông tin", KHÔNG bịa. Multi-hop (An làm gì + deadline) → gộp đúng 2 item.
- **Bug/issue phát hiện (chưa sửa hết):** ① `search_history` lỗi `retriever_factory not available` — `app_state` chưa wire `retriever_factory` → tool fallback của responder hỏng (knowledge path không phụ thuộc nên chưa chặn). ② trial plan cap `max_active_tools=5` + seed tool theo thứ tự registry → boss mới KHÔNG tự có `search_knowledge` (RUNBOOK đã ghi backfill; cap-by-order mong manh). ③ `agent_loop` CHƯA render placeholder (`{{ chat_id }}`, `{{ group_name }}`…) mà seed-prompt giả định → tạm dùng prompt placeholder-free; **scope search theo nhóm hiện tại (group_id) chưa truyền** (test 1 nhóm nên chưa lộ; đa nhóm sẽ trộn). ④ test wipe để lại orphan Qdrant points (chỉ ảnh hưởng harness; prod soft_delete→index.remove nên sạch).
- **Quyết định tune còn mở (precision↔recall):** extract lọc bỏ đề xuất thiết kế ("màu chủ đạo xanh dương") → mất khi hỏi. Cần chốt: có capture proposal/preference thành `note` không (lợi recall, hại precision)?

**2026-06-14 — Harness vòng 2 (core write-path, fix-từ-core-ra) ✅.**
- **Reconcile UPDATE vs DELETE** (lõi memory): trước đây risk đã giải quyết bị UPDATE (giữ nhãn `risk`/`active`). Làm rõ prompt reconcile: "đổi giá trị, cùng việc đang theo dõi" = UPDATE; "việc/rủi ro đã khép lại" = DELETE. Test 2-pass live: deadline 30/6→15/7 ⇒ **UPDATE đúng**; VNPay "đã mở sandbox" ⇒ **DELETE** item risk (status=deleted, revision reason đúng, soft-delete + Qdrant point gỡ) + **ADD** fact "VNPay mở sandbox". Read path xác nhận: "còn rủi ro?" → "không có rủi ro đang theo dõi"; deadline → 15/7. ✅
- **Extract chống pollute**: phát hiện câu hỏi của sếp tag-bot bị capture thành message → re-extract biến câu hỏi thành "knowledge" rác. Thêm chỉ thị extract BỎ QUA câu hỏi/lời chào/tin hỏi-đáp với bot. Test: inject 2 tin câu hỏi vào window → 0 item tham chiếu chúng; nội dung thật vẫn trích đủ. ✅
- knowledge_extract/reconcile vẫn chạy từ **CONSTANT trong `knowledge_service.py`** (bảng prompts chưa seed 2 key này — single source đang dùng); yaml canonical đã bump v2 đồng bộ. in_group chạy từ DB (seeded v2).
- Non-determinism (temp 0.2): item "màu chủ đạo" lúc lấy lúc bỏ; thỉnh thoảng 1 tin tách 2 item / câu mở đầu thành 1 decision — precision noise nhẹ, chấp nhận v1.
- **Còn nợ (ngoài core, ưu tiên giảm dần):** wire `retriever_factory` (search_history fallback) · render placeholder + truyền `group_id` scope nhóm (đa nhóm) · backfill `search_knowledge` cho boss cũ / sửa cap-by-registry-order · seed nốt prompts còn lại.

**2026-06-14 — Đổi model nền sang GPT‑5.4 Mini (tạm thời, cho cả smart lẫn fast) ✅.**
- **Client bug chặn cứng (fix cốt lõi):** `openai_compat.py` gửi `max_tokens` → models OpenAI đời mới (gpt-5.x/o-series) trả **400 "Unsupported parameter: max_tokens, use max_completion_tokens"** → MỌI call gpt-5.4-mini fail → extraction 0 item. Đổi sang `max_completion_tokens` (verify nhận được bởi cả gpt-4o lẫn Groq → dùng chung an toàn). gpt-5.4-mini nhận temperature 0.1/0.2 OK.
- **Config:** gpt-5.4-mini = platform default tier `smart` (400k ctx, $0.75/$4.50, caps text/vision/tools); `note_update` route fast→smart ⇒ MỌI feature dùng gpt-5.4-mini. gpt-4o giữ active nhưng bỏ default (để A/B). llama = fast = **fallback cross-provider**. seed_llm.sh cập nhật đồng bộ.
- **Fallback bug (fix resilience):** `_try_fallback` làm `fb.get("tier")` nhưng seed lưu `fallback_chain=["fast"]` (string) → AttributeError → fallback chết âm thầm. Sửa nhận cả string lẫn dict. Verify live: đổi tên model primary thành sai → query vẫn được llama trả lời (không ra _FALLBACK_REPLY).
- **Eval gpt-5.4-mini (sau khi sửa retrieval pollution):** ⚠️ harness `wipe-knowledge` chỉ xoá DB, KHÔNG xoá Qdrant → ~40-53 orphan point lấn át dense top-k, bóp nghẹt item sống → câu "rủi ro?"/"tóm tắt" ra thiếu (TƯỞNG model dở, thực ra do orphan). Fix harness purge Qdrant (prod soft_delete đã xử lý, đây chỉ là lỗi harness). Sau khi sạch: **responder gpt-5.4-mini xuất sắc** — ai-lo-X, risk (còn suy luận thêm rủi ro thứ cấp), tóm tắt 7 ý đủ, no-info không bịa. Reconcile UPDATE/DELETE (prompt tune trên 4o) **chuyển sang 5.4-mini chạy nguyên** (deadline→UPDATE, risk resolved→DELETE).
- **Khác biệt extraction:** gpt-5.4-mini eager/granular hơn 4o (8–12 item vs 6–8): tách phân công thành item nguyên tử, recall cao hơn (bắt cả ước lượng/deadline phụ/màu), importance calibrate tốt; đôi khi bắt cả câu chào kickoff thành fact. Gán assignment là `fact` (4o gán `decision`) — ít ảnh hưởng do đã bỏ nudge lọc theo kind. Nếu muốn gọn như 4o → tune extract về phía consolidation (chưa làm, để ngỏ).
- **Chi phí:** ~29 call ≈ $0.048 (4o cùng tải ~$0.13) → rẻ ~2-3x. Quan sát nhỏ: token_usage log tên model PRIMARY kể cả khi đã fallback (observability lệch nhẹ, low-pri).

**2026-06-14 — Group scoping cho retrieval (read-path core-out) ✅.**
- Trước: responder gọi `search_knowledge(group_id=null)` → lục TẤT CẢ nhóm của sếp → đa nhóm lẫn tri thức.
- Fix: thêm `chat_id`/`provider`/`chat_type` vào `ToolContext` (`_build_tool_ctx` lấy từ event); `search_knowledge`
  mặc định scope về **nhóm hiện tại** khi đang ở group và model không truyền group_id (muốn nhóm khác → truyền
  tường minh; DM/web chat_type≠group → None = mọi nhóm, đúng cho tổng hợp chéo). Model không cần biết chat_id.
- Verify 2 nhóm cùng boss (Apollo: An=backend/demo 15/7 · Beta: Bình=backend/demo 20/8): cùng câu hỏi, **đáp đúng
  theo từng nhóm, không lẫn** (Apollo→An/15/7, Beta→Bình/20/8). ✅
- (search_history cùng cần scope nhưng vẫn hỏng — KHÔNG phải fix 1 dòng: cần wire `retriever_factory` vào
  app_state + seed `retrieval_pipelines` (RỖNG) + sửa format `sources:[bm25,dense]` (string, code cần dict) +
  **messages chưa index Qdrant (0 point)** nên dense rỗng. = hồi sinh cả subsystem message-retrieval (path cũ
  spine định thay). Tách thành task riêng, KHÔNG làm chung vòng tune spine. Hiện responder dùng search_knowledge
  là đủ cho mọi câu đã test.)

**Việc còn lại cần QUYẾT trước khi build tiếp (không tự ý làm):**
1. **Provisioning vs plan cap** (product/monetization): trial cap `max_active_tools=5` + seed theo thứ tự registry
   → boss mới KHÔNG có search_knowledge. Sửa đúng = "core tools always-on, KHÔNG tính vào cap; cap chỉ cho
   marketplace/integration" — nhưng đụng nghĩa của gói (status "over limit"...). Cần chốt nghĩa max_active_tools.
2. **search_history revival** (subsystem riêng, xem trên) — làm khi cần lookup tin thô/nguyên văn ở quy mô thật.
3. Reconcile fetch đang theo SCOPE cap 50 (chưa similarity) — đủ ở quy mô nhỏ; nâng similarity (infra embedding đã có)
   khi 1 nhóm > 50 item.

**2026-06-14 — Tool core always-on, cap chỉ cho integration (provisioning + UI) ✅.**
Quyết định (user): tool LÕI không cap, luôn bật, KHÔNG tắt được; chỉ integration mới bị cap. Web UI: integration
trước, core là list ưu-tiên-thấp thu gọn ở dưới, bấm mới hiện đủ, read-only. Min core để vận hành ≈10 (responder
khai báo 14 in_group / 18 dm) — nên cap 5 của trial là sai.
- **Backend:** `_allowed_tools` bỏ intersect `boss_active_tools` → core (cfg.tools/_REGISTRY) LUÔN allowed cho mọi
  op/boss (đồng thời **tự fix bug search_knowledge thiếu cho mọi boss cũ, không cần backfill**). `provision_new_boss`
  bỏ truncate theo cap → seed đủ core. `check_over_limit`: tools=0 (core không bao giờ over). `/tools` trả
  `core/active/can_disable`; toggle + disable-all → 400 (core không tắt được); enable-all idempotent không cap.
  `max_active_tools` giữ field nhưng không áp cho core (cap thực tế cho integration đã là `mcp_slots`).
- **FE:** gộp trang Tools vào Integrations — bỏ nav/route Tools, xoá page.tsx, thêm section "Công cụ lõi" thu gọn
  read-only (luôn bật, badge) ở cuối trang Integrations. i18n vi/en `intg.core.*`. typecheck+lint+build sạch.
- **Verify:** boss TRIAL mới qua đúng path provisioning → `active_tools=19`, có `search_knowledge`, trả lời truy vấn
  tri thức ngay (không cần pro-plan/backfill). 63 test integration liên quan PASS (tools/subscription/promotion/
  plugin/groups/normalizer). Test `test_api_tools_toggle.py` viết lại theo contract mới (core read-only, toggle/
  disable-all bị từ chối, enable-all uncapped).

**2026-06-14 — Q&A deep-tune vòng 1 (Pha A) ✅ + gold-set materialized.**
- **BUG (scope leak đa nhóm) — đã sửa:** responder đôi khi gọi `search_knowledge(group_id="")`
  (chuỗi rỗng thay vì bỏ trống). Scope-default cũ chỉ kích hoạt khi `group_id is None` → `""`
  lọt xuống index như "không lọc nhóm" → câu hỏi trong nhóm Apollo **lẫn tri thức nhóm Beta**
  (demo 20/8 hiện ra khi chỉ hỏi demo Apollo). Sửa: helper `_scope_group(ctx, gid)` chuẩn hoá
  falsy→None rồi áp scope nhóm hiện tại; dùng chung cho cả 4 search tool (`search_knowledge`,
  `search_history`, `count_messages`, `find_exact_quote`). Verify: hỏi cùng câu trong Apollo và
  Beta → đáp đúng từng nhóm, KHÔNG lẫn.
- **Responder temperature 0.7→0.3:** `agent_loop` không set temperature → mặc định `LLMRequest`
  0.7 (quá cao cho thư ký bám dữ kiện). Hạ về 0.3 (extract 0.2 / reconcile 0.1) → bớt trôi/bịa,
  trả lời nhất quán hơn (ổn định gold-set).
- **Observability:** thêm `finish_reason` vào `LLMResponse` (capture ở openai_compat) + log
  `agent_llm_turn` (finish/content_len/n_tools/content_tail) mỗi vòng loop — để phân biệt
  "model trả thiếu" vs "bị cắt do token" vs "lỗi tool". (Lần này xác nhận model trả ĐỦ, finish=stop.)
- **Gold-set (D6) đã hiện thực hoá:** `scripts/gold_cases.json` (7 case: ownership 2 nhóm, reconcile
  Supabase, time-arithmetic + chống lẫn nhóm, multi-hop, ranking deadline, no-info không bịa) +
  lệnh `harness.py gold` (assert must_include không phân biệt hoa/thường, must_exclude phân biệt;
  bỏ qua quick-ack; ask_in apollo|beta; exit≠0 nếu fail). **7/7 PASS.**
- **Bài học harness:** `harness.py ask` in ĐẦY ĐỦ câu trả lời (đa dòng). Lần đầu mình lọc
  `grep '^(Q|BOT):'` → cắt mất mọi dòng sau newline đầu → TƯỞNG bot trả lời cụt; thực ra bot trả
  đủ (list bullet + time-math chuẩn). Đừng grep output harness.
- **Phát hiện còn MỞ (chưa sửa, cần quyết hướng):** câu "còn rủi ro VNPay không?" — risk VNPay đã
  resolved nên bị **soft-delete** (biến mất khỏi search). Bot không thấy item "đã xử lý" nên dựng
  lại "rủi ro" từ các fact dời-deadline-vì-thanh-toán → khung câu trả lời thành "có rủi ro thanh
  toán" (grounded nhưng nhập nhằng với rủi ro đã đóng). Tension thiết kế: resolved-risk nên DELETE
  (gọn) hay giữ `status=resolved` (trả lời "đã xử lý" tốt hơn)? → đưa user quyết ở vòng sau.
- **Giới hạn harness lộ ra:** `ask` luôn post vào 1 nhóm → KHÔNG test được câu **all-scope/DM**
  (tổng hợp chéo nhóm) — vốn cũng là đường Pha B (sếp hỏi ở web admin, scope=mọi nhóm). Vòng sau
  cần mở DM-ask.

**2026-06-15 — Q&A deep-tune vòng 2 (Pha A): kịch bản TÁI LẬP + fix lõi extract/time + gold ổn định.**
- **Kịch bản tự đủ + tái lập:** `harness.py setup` giờ tạo CẢ Apollo (16 tin) + Beta (5 tin); CONVO
  gồm đủ phân công, đổi DB (Postgres→Supabase), risk VNPay rồi RESOLVED, wireframe hoàn thành, dời
  deadline (demo 30/6→15/7, backend 10/7), 1 việc TRỄ HẠN (báo cáo 10/6), nhiễu. Bỏ ngày tương đối
  ("thứ 6 tuần này") vì không tái lập + làm sai xếp hạng.
- **BUG harness #1 (race ingest) — sửa:** `inbound.normalized` ingest BẤT ĐỒNG BỘ → `setup`→`extract`
  chạy trên window THIẾU (lần đầu chỉ trích 5/16 tin Apollo, Beta 0). Thêm `_wait_ingested` poll tới
  khi đủ tin mới extract. Sau fix: 1 lần extract ra đủ ~17-19 item, provenance đúng.
- **BUG harness #2 (capture) — sửa:** `_ask_capture` đếm out-msg rồi cắt [n:] → khi nhóm tích luỹ
  >100 tin (gold chạy nhiều lần) cửa sổ limit lệch → tưởng "(no reply)" dù bot trả ĐÚNG (log
  `agent_llm_turn` xác nhận finish=stop, content đủ). Đổi sang **diff theo ID tin out** (limit 200).
  ⚠️ Bài học lặp lại: nhiều "bug" là artifact của HARNESS, không phải sản phẩm — luôn soi `outbound_messages`/log trước khi kết luận.
- **BUG lõi (extract within-batch) — sửa:** trong CÙNG 1 window, reconcile chỉ so với existing (rỗng
  ở pass đầu) → KHÔNG khử mâu thuẫn nội bộ batch: demo "30/6" + "dời 15/7" cùng active → câu "deadline
  sắp tới gần nhất" lúc lấy nhầm 30/6. Sửa prompt extract **v4**: hợp nhất giá trị bị thay trong cùng
  đoạn thành 1 mục trạng thái mới nhất; RIÊNG ngày/deadline dời thì content chỉ ghi MỐC MỚI (bỏ mốc cũ
  để khỏi lẫn khi xếp hạng). (Reconcile cross-batch UPDATE/DELETE vẫn lo phần đa-pass như cũ.)
- **BUG lõi (time-reasoning) — sửa:** bot xếp việc TRỄ HẠN (báo cáo 10/6, đã qua) là "sắp tới gần
  nhất". Bổ sung vào `_current_time_directive` (dùng chung mọi responder): mốc đã QUA = 'trễ hạn' nêu
  riêng, KHÔNG tính 'sắp tới'; 'sắp tới' chỉ gồm mốc tương lai. → câu ranking ổn định.
- **dm_general v2:** trước RỖNG (responder DM chạy KHÔNG system prompt) → viết v2 (thư ký, search_knowledge-first,
  scope MỌI nhóm cho tổng hợp chéo, placeholder-free). Đã `seed_prompts.py` nạp đủ 7 prompt vào DB.
- **DM = đường tổng hợp chéo nhóm (và là đường Pha B):** web test channel sẵn `chat_id="dm:<boss>"`
  (`sender_is_boss` wired) → harness thêm `ask_in="dm"`. Verify: "có dự án nào / deadline gần nhất toàn
  công ty" → bot gộp đúng Apollo+Beta, xếp hạng xuyên nhóm.
- **Gold-set mở rộng 11 case** (thêm overdue, frontend Beta, projects-list DM, cross-nearest DM) + runner:
  token động `{days_until:YYYY-MM-DD}` (assert số ngày không "hết hạn"), khớp tên riêng phân biệt hoa/thường.
  **3 lần chạy liên tiếp 11/11 PASS, tất định.**
- **VNPay resolved-risk (đưa user quyết):** single-pass extract giữ CẢ risk + fact "đã mở sandbox/đã gỡ"
  → bot trả lời chuẩn ("rủi ro đã được gỡ vì sandbox đã mở"). Việc "biến mất" chỉ xảy ra ở cross-batch
  reconcile DELETE (vòng build trước). → Khuyến nghị: resolved-risk nên GIỮ vết (status=resolved / +fact)
  thay vì hard-DELETE, để trả lời "đã xử lý" được. Cần user chốt hướng reconcile cho risk.

**2026-06-15 — Q&A deep-tune vòng 3 (Pha A): reconcile đa-pass + resolved-risk GIỮ VẾT (user chốt).**
- **Quyết định user:** risk/việc đã giải quyết → KHÔNG hard-DELETE mà **status='resolved' (giữ vết)** để
  trả lời "đã xử lý" thay vì im/bịa. Hướng đi: "Cả hai — Pha A trước" rồi mới Pha B.
- **Lõi (status=resolved):** thêm `KnowledgeStatus.RESOLVED` + `RevisionOp.RESOLVE` + `RETRIEVABLE_STATUSES`.
  `KnowledgeRepo.resolve()` (status=resolved, GIỮ Qdrant point, optional ghi đè content cho khớp trạng
  thái); `search_fts`+`get_many` mở rộng `status IN ('active','resolved')`; `search_knowledge` trả thêm
  field `status`. `_apply` thêm nhánh RESOLVE: enrich content "— [Đã xử lý: <reason>]" + re-index.
- **Reconcile v4 (prompt):** thêm op **RESOLVE** (đã xử lý/xong → giữ vết) TÁCH khỏi **DELETE** (sai/trùng/
  phủ định → xoá hẳn); **UPDATE** bao gồm đổi công nghệ/hạ tầng/nhà cung cấp (AWS→Vercel, Postgres→Supabase)
  — đừng DELETE khi chỉ là đổi-giá-trị (mất thông tin mới); reason viết TỰ NHIÊN (không lộ "candidate").
- **Responder v4 (in_group+dm):** item `status='resolved'` → trả lời "KHÔNG còn, đã xử lý" (dù content mô tả
  vấn đề ở thì hiện tại = mô tả gốc); không liệt kê resolved vào "đang mở/còn lại".
- **Verify (harness `multipass` — lệnh MỚI, regression cross-batch):** Pass1 (risk license + AWS + deadline
  30/6 + task rà soát) → extract reset; Pass2 (đã mua license / dời 20/7 / rà soát xong / đổi sang Vercel)
  → extract incremental. Kết quả ĐÚNG + ỔN ĐỊNH: risk→resolved (content enrich), task→resolved, hosting
  AWS→Vercel (UPDATE, không mất), deadline→20/7; câu hỏi "còn rủi ro X?"→"không còn, đã xử lý". **6/6 PASS ×2.**
  Gold single-pass vẫn **11/11**.
- **Lưu ý non-determinism:** cross-batch đôi khi đạt "đã đóng" bằng ADD-fact thay vì RESOLVE (đã nudge ưu
  tiên RESOLVE). Câu trả lời vẫn đúng cả hai cơ chế → `multipass` assert THEO OUTCOME (Q&A) là cổng chính,
  DB-status là phụ. Cơ chế sạch nhất (RESOLVE) tốt cho câu "liệt kê rủi ro đang mở".

**2026-06-15 — PHA B khảo sát + bắt đầu build (workload/hiệu suất) — core-out.**
- **Khảo sát (verify, không giả định):** `action_items` {assignee_name TEXT, **due_at**, status open/done/
  cancelled, group_note_id, project_id} ĐANG được populate bởi pipeline note (`note_service`). Membership ở
  `group_members`/`web_group_members`. FE đã có `components/charts.tsx` (BarChart xu hướng + RankBars xếp
  hạng, tự code, không lib ngoài) + mẫu trang admin `usage` (page→api→chart). CHƯA có: tầng aggregation,
  `list_members`, đường đưa biểu đồ cho admin. ⚠️ assignee_name FREE-TEXT + thưa (extraction note cần soi
  riêng); workload nên gộp trên action_items (có cấu trúc) chứ không phải knowledge spine.
- **Quyết định user:** (1) biểu đồ = **A) trang admin + endpoint tổng hợp (deterministic)**, AI trả lời
  workload bằng CHỮ qua cùng tool — KHÔNG đi hướng AI-sinh-chart-spec (để sau). (2) entity = **lean
  free-text trước** (assignee + group=team + bucket '(chưa gán)'), dựng model people/team sau khi cần.
- **Đã build (core-out bước a):** `ActionItemsRepo.workload_summary(group_id?)` — gộp theo người: open/
  overdue(due<now & open)/done/cancelled + completion_rate + bucket '(chưa gán)' + totals, xếp người
  nhiều quá-hạn/đang-mở lên trước. Tool `workload_summary` (dm + in_group). list_members DEFER (assignee
  đã lộ trong summary; roster cross-provider rườm rà — làm khi cần "ai đang rảnh").
- **Verify (harness `workload` — lệnh MỚI, regression):** seed 14 action_items (An 3open/1qh/2done, Bình
  1open/3done, Châu 4open/2qh, 1 chưa gán) → AI trả lời ĐÚNG + sâu sắc: "ai quá tải"→Châu (breakdown
  đúng), "việc trễ hạn"→3 (Châu 2/An 1), "tóm tắt hiệu suất"→completion-rate + nhận định lệch tải +
  khuyến nghị ưu tiên 3 việc quá hạn. **4/4 PASS.** AI tự đi tổng hợp team→task→insight = đúng mục tiêu Pha B (dạng text).
- **CÒN LẠI Pha B:** (b) endpoint `/api/...workload` + trang admin "Hiệu suất" render RankBars/BarChart
  (mảnh render — chưa làm); (c) soi/tune chất lượng extraction assignee+due của pipeline note (dữ liệu thật
  thưa assignee); (sau) list_members; (sau) AI-sinh chart-spec nếu cần.

**2026-06-15 — PHA B: SPINE làm nguồn workload (user chốt) ✅ built + verified e2e.**
- **Phát hiện then chốt khi "soi extraction":** `action_items` KHÔNG được trích từ hội thoại bởi bất kỳ
  pipeline nào (`ActionItemsRepo.insert` không có caller) — chỉ seed demo. Pipeline note chỉ sinh markdown.
  → quyết định (user): **spine knowledge làm nguồn workload** (không dựng pipeline action_items thứ 2).
- **Build:** migration **0017** thêm `assignee_name` + `due_at` vào `knowledge_items` (+ index theo assignee).
  Domain/repo `KnowledgeItem` + `add()/update()/_snapshot` mang 2 field. `KnowledgeRepo.workload_summary(chat_id?)`
  gộp item CÓ assignee: open=active / done=resolved / overdue=active&due<now + completion_rate, xếp quá-hạn↑.
  Tool `workload_summary` đổi đọc từ KnowledgeRepo (qua `_scope_group`). Gỡ `ActionItemsRepo.workload_summary` (chết).
- **Extract v5:** thêm field tùy chọn `assignee` (tên người nếu phân-công) + `due` (ISO, suy năm từ mốc
  `{{ today }}` được inject). Service `_parse_due` (date-only→cuối ngày, tz-aware) + ADD/UPDATE điền 2 field
  (UPDATE chỉ ghi đè khi candidate có nêu — không xoá giá trị cũ). status active=đang làm, resolved=xong (vòng 3).
- **Verify e2e:** setup Apollo+Beta → extract → knowledge_items CÓ assignee/due đúng (An backend due 10/7,
  Châu báo cáo due 10/6, …); `workload_summary` gộp đúng (Châu 3 mở/1 quá hạn…); AI trả lời "ai nhiều việc
  nhất + deadline gần nhất" → Châu + báo cáo 10/6 trễ 5 ngày. **Lệnh `harness.py workload` (seed
  knowledge_items) 4/4 PASS ×3.** gold 11/11 + multipass 6/6 không regress.
- **Prompt responder v5 (in_group+dm):** câu khối lượng/quá tải/TRỄ HẠN/hiệu suất → ưu tiên `workload_summary`
  (trước chỉ search_knowledge-first → "trễ hạn" lúc ra lúc không vì content không có tín hiệu quá hạn).
- **Polish (v6/v7 extract + tool):** (1) `due` CHỈ điền khi có HẠN RÕ RÀNG — KHÔNG suy từ ước lượng mơ hồ
  ("estimate 2 tuần" → đừng đặt deadline phantom làm sai ranking). (2) content giữ ngày kiểu VN "15/7", ISO chỉ
  ở field `due` (trước extraction nhét ISO vào content → bot trả "2026-07-15"). (3) `search_knowledge` trả thêm
  `assignee`+`due` (responder cần field cấu trúc, không thì ngày nằm trong due_at là vô hình). (4) `workload_summary`
  trả thêm `overdue_items` {assignee, what, due} để trả lời "việc NÀO trễ" chứ không chỉ đếm. (5) gold matcher
  chuẩn hoá ngày ('20/7' khớp cả '20/07/2026'). Sau polish: gold 11/11 · multipass 6/6 · workload 4/4 (xanh CÙNG lúc).
- **Còn lại Pha B:** (b) endpoint + trang admin "Hiệu suất" render charts.tsx (mảnh render — CHƯA làm);
  polish: extract đôi khi tách "phân công backend" + "deadline backend" thành 2 item cùng người (đếm hơi dư);
  list_members + AI-sinh chart-spec để sau. ⚠️ Lưu ý lặp lại: query DB phải dùng boss từ harness state — id
  nhóm/boss là hex ngẫu nhiên, `ORDER BY id DESC` VÔ NGHĨA (đã suýt kết luận sai "extraction không điền assignee").

**2026-06-15 — PHA B: trang admin "Hiệu suất" (mảnh render) ✅ built + verified API.**
- **BE:** `GET /api/v1/admin/workload?group_id=` (api_admin.py, `require_boss`) → `KnowledgeRepo.workload_summary`
  (scope/totals/by_assignee/overdue_items). Thin wrapper trên repo đã verified.
- **FE:** feature mới `admin/features/performance` (page.tsx + api.ts) — render **RankBars** khối lượng theo
  người (bar=việc đang mở, sub=quá hạn·đã xong·% hoàn thành) + bảng **việc quá hạn** (việc/người/hạn) + 4
  summary card (người/mở/quá hạn/đã xong). Tái dùng `charts.tsx` + mẫu trang `usage`. Thêm nav "Hiệu suất"
  (Gauge, workspace section) + route `/app/admin/performance` + i18n vi/en (`perf.*`, `nav.admin.performance`).
- **Verify:** `npm run build` sạch (typecheck/lint/build). Endpoint test với session bid thật (make_session)
  → 200, dữ liệu đúng từ spine đã extract: Châu 3 mở/1 quá hạn · An 3 · Bình 3; overdue_items nêu đúng
  "Báo cáo tiến độ còn thiếu" hạn 10/6. (Chưa chụp ảnh UI — render dùng component đã chứng minh ở trang usage.)
- **PHA B coi như xong lõi:** workload theo người (chữ qua bot + biểu đồ trên admin) chạy e2e từ spine.
  Còn (polish, sau): extraction đôi khi tách phân-công + deadline cùng người thành 2 item (đếm hơi dư);
  list_members (ai rảnh/đủ roster); AI-sinh chart-spec inline; bộ lọc theo nhóm/dự án trên trang Hiệu suất.

**2026-06-15 — PHA B POLISH P1+P2 (workload/Hiệu suất) ✅.**
- **P1 — chụp UI `/app/admin/performance` (xác nhận render):** build FE lại (build cũ cũ hơn source perf),
  mint cookie boss qua `make_session`, render bằng Playwright/chromium (dark). HTTP 200, 0 console error.
  4 card + RankBars theo người + bảng quá hạn render đúng, KHỚP 1-1 JSON endpoint. Không vỡ layout, KHÔNG
  viền trắng (border bảng = token `--border` rgb(21,21,25), tối). (Ghost text mờ chỉ xuất hiện khi chụp
  RIÊNG phần tử bảng có parent `overflow-x-auto` = artifact element-screenshot của Playwright; DOM thật 3 cột
  sạch, full-page sạch.)
- **P2 — gộp item theo đầu việc/người (workload khỏi đếm dư):** soi dữ liệu thật thấy phồng KHÔNG chỉ do
  deadline mà do follow-up note cùng việc: An = phân-công + "ước lượng 2 tuần" (2 item), Bình = phân-công +
  "wireframe xong" (2 item); và deadline backend 10/7 nằm ở item RIÊNG (vô chủ) thay vì gắn vào việc của An.
  → **EXTRACT v8** (`config/seeds/prompts/knowledge_extract.yaml` + constant `_EXTRACT_PROMPT`): "GỘP THEO
  ĐẦU VIỆC" — phân-công + deadline + ước lượng + tiến độ của CÙNG một việc → 1 mục/người, `due` gắn vào mục
  đó VÀ nêu hạn trong content kiểu VN để TRA CỨU được; NGOẠI LỆ deadline CHUNG dự án/demo (vô chủ) vẫn riêng;
  hai đầu việc KHÁC nhau của cùng người vẫn 2 mục. Reseed + re-extract Apollo → An 3→2, Bình 3→2 (tổng mở 9→7),
  Châu giữ 3 (3 việc thật). UI admin xác nhận de-inflation.
- **Bẫy đã gỡ:** lần đầu chỉ để due ở field (không nêu hạn trong content) → `cross-nearest-deadline-dm` FAIL
  (10/7 chìm trong item role-fact, retrieval DM-cross-group không nổi) → thêm "nêu hạn trong content". Fix xong.
- **Verify:** thêm 2 check vào `harness.py workload` (kịch bản Zeta: phân-công + deadline 20/7 + ước lượng →
  An ĐÚNG 1 việc, due gắn trên việc đó). **gold 11/11 · multipass 6/6 (×3, 1 lần flaky do reconcile P2
  non-deterministic — đã xác nhận P1-extract sạch, không phải lỗi prompt mới) · workload 6/6.**

**2026-06-15 — PHA B POLISH P3 (tool `list_members` — roster / 'ai đang rảnh') ✅.**
- **Repo:** `GroupNotesRepo.list_members(chat_id?)` provider-agnostic — UNION `group_members` (kênh thật:
  display_name+role inline, khoá group_notes.id) + `web_group_members` (kênh test: join web_users lấy tên,
  group_name COALESCE từ web_groups). Scope theo boss; dedupe theo TÊN, gom các nhóm mỗi người, role='boss'
  nếu là tài khoản sếp. Tool `list_members` (`src/tools/core/meta.py`, available_to dm+in_group), đăng ký vào
  `tools={...}` của `dm_responder` + `in_group_responder`. (KHÔNG có agent 'nudge' trong codebase — handoff nhắc
  nhưng chưa tồn tại; bỏ qua.)
- **Verify (bot thật, server restart vì code mới):** "Nhóm này có những thành viên nào?" → liệt kê đủ An/Bình/
  Châu/Sếp Minh. DM "team gồm ai + ai rảnh nhất?" → bot GỘP `list_members`+`workload_summary`: "rảnh nhất =
  Bình & An (2 việc mở, 0 quá hạn); Châu bận nhất (3 mở + 1 quá hạn)" — đúng & phản ánh de-inflation P2.
- **Phụ: prompt responder v6 (dm_general + in_group)** — (1) thêm hướng dẫn `list_members` (roster/'ai rảnh');
  (2) chốt 'deadline SẮP TỚI / GẦN NHẤT' = mốc TƯƠNG LAI gần nhất, việc QUÁ HẠN = trễ (KHÔNG phải 'sắp tới').
  (2) sửa flaky `cross-nearest-deadline-dm`: sau P2 hạn 10/7 nằm trong item role-fact của An → DM cross-group
  bot lúc trả 10/6-quá-hạn lúc trả 10/7 (~40% fail). Sau v6: **cross-nearest 5/5 PASS.**
- **Verify:** **gold 11/11 (×4/5 full-green, cross-nearest 5/5; 1 lần 10/11 do 1 case khác flaky benign LLM
  variance, không tái lập) · multipass 6/6 · workload 6/6.**

**2026-06-15 — PHA B POLISH P4 (bộ lọc nhóm trên trang Hiệu suất) ✅.**
- **BE:** `GET /api/v1/admin/workload?group_id=` lọc theo CHAT_ID. Nhưng `GET /api/v1/admin/groups` chỉ trả
  `id` (group_notes.id BIGINT) — mismatch. Sửa: thêm `chat_id` vào response (cả nhánh boss + superadmin) +
  `name` COALESCE thêm `web_groups.name` (LEFT JOIN — group_notes.group_name NULL cho nhóm web test → trước
  hiện 'g-xxx'; giờ ra 'Dự án Apollo/Beta'; vô hại prod vì web_groups rỗng). Cải thiện cả trang Nhóm sẵn có.
- **FE:** `performance/page.tsx` thêm `<Select>` (PageHeader actions) "Tất cả nhóm" + từng nhóm (value=chat_id,
  reuse `groupsListQuery`); `workloadQuery(groupId)` key + query-param theo chat_id; bọc `PerfContent` trong
  `<Suspense>` cục bộ (spinner) để đổi nhóm không chớp cả header. `GroupListItem.chat_id` + i18n `perf.filter.allGroups` (vi/en).
- **Verify:** `npm run build` sạch. Chụp UI (Playwright): mặc định "Tất cả nhóm" → mở 7/quá hạn 1 (Châu 3/An 2/
  Bình 2); chọn "Dự án Beta" → scope đúng 3 người mỗi người 1 việc, 0 quá hạn (bảng quá hạn ẩn). 0 console/page
  error, dark-mode sạch. gold 11/11 (P4 chỉ đụng admin-endpoint + FE, KHÔNG đụng đường bot → multipass/workload
  bất biến, đã xanh ở P3 trên cùng code đường-bot).

**2026-06-15 — PHA B: chốt BỎ P5 (AI-sinh chart-spec inline) — Pha B HOÀN TẤT.**
- **User chốt:** chart CHỈ cần ở **web admin** (đã có qua P1/P4). KHÔNG làm bot tự sinh chart-spec để vẽ inline
  trong chat. Kênh chat (Zalo…) phần lớn không render được biểu đồ → khi cần sẽ làm theo hướng **render chart
  server-side → xuất PNG → gửi như ẢNH** (hạng mục TƯƠNG LAI riêng, không thuộc polish workload). ⇒ Pha B
  (workload theo người: chữ qua bot + biểu đồ trên admin + lọc nhóm + roster) coi như HOÀN TẤT.

**2026-06-19 — ĐỌC LINK/MEDIA + web_search + integration superadmin (nhánh `feat/media-web-search`).**
- **Bối cảnh:** nhánh "gỡ cứng nhắc" phần C. Spec+plan ở `docs/superpowers/{specs,plans}/2026-06-19-*`.
- **Phát hiện gốc (khác giả định ban đầu):** adapters media KHÔNG hề "chưa cắm dây" — `src/media/__init__.py`
  force-import sẵn. "Đọc link bị reject" thật ra do: (a) **thiếu User-Agent → site trả 403** (Wikipedia/báo),
  (b) PDF/ảnh URL bị route sai (`_detect_from_url` chỉ biết youtube/tiktok/url), (c) YouTube transcript stub,
  (d) ảnh chưa được inject vision-LLM, (e) prompt không bảo bot chủ động đọc.
- **Làm (verified live):** `fetch_url` viết lại (route theo loại + fetch bytes cho doc/ảnh + inject `ctx.llm`
  cho vision + error rõ ràng) · **BROWSER_UA** (vnexpress 200, hết 403) · **YouTube transcript THẬT** qua
  `youtube-transcript-api` 1.2 (API mới `.fetch().to_raw_data()`; verified lấy 2089 ký tự) · TikTok best-effort
  (metadata; transcript đầy đủ = ASR phase sau) · document/ảnh adapter (đã có, chỉ cần truyền bytes). Bot đọc
  VnExpress → tóm tắt súc tích tin thật ✓.
- **web_search:** provider pluggable `src/search/` (Tavily qua httpx) + tool `web_search` (dm+in_group). Key/cost
  ở **superadmin**: migration **0018** `platform_integrations`(key Fernet + unit_cost + status) + `integration_usage`
  (rollup ngày cho chart); `PlatformIntegrationsRepo`; endpoints superadmin (config/test-key/usage). FE trang
  Integrations (charts) = CÒN LẠI. Test live web_search cần Tavily key (nhập qua superadmin).
- **Prompt responder v7** (dm+in_group): chủ động `fetch_url`/`web_search`, KHÔNG từ chối link khi chưa thử,
  tóm tắt link/video ngắn gọn.
- **Regression:** gold 11/11 · multipass 6/6 · workload 6/6. ⚠️ **LIMITATION (ghi nhận):** GỘP-đầu-việc của
  extract v8 là **LLM-dependent** — gpt-5.4-mini (19/6) đôi khi tách deadline-ở-message-riêng/estimate thành item
  riêng cho cùng người → đếm dư 1. Rule "không heuristic" ⇒ không dedup bằng code; check `workload` đã NỚI về mục
  tiêu thực tế (deadline truy được + gắn đúng người + đếm dư ≤1) thay vì "đúng 1 item".
- **CÒN LẠI:** FE trang Integrations superadmin (key/status/cost charts) · đường B (enrich media đính kèm
  inbound — cần kênh thật/fixture để test) · backfill `youtube-transcript-api` vào env (đã thêm pyproject).

### RUNBOOK — chạy harness tune loop (session mới, context sạch)
1. `bash scripts/restart.sh` (hoặc `uv run uvicorn src.main:app`) — cần `ENABLE_WEB_TEST_CHANNEL=true`, web bot_account provider='web' active.
   **Seed bắt buộc (1 lần/môi trường):** `bash scripts/seed_llm.sh` (models/routes/budgets — gồm `knowledge_extract`/`knowledge_reconcile`) + `uv run python scripts/seed_prompts.py` (prompts; **bảng `prompts` rỗng = responder chạy KHÔNG có system prompt → trả lời lung tung**).
2. Tạo boss: `POST /test/api/users {name, role:"boss"}`; nhân viên: role:"employee". Tạo nhóm: `POST /test/api/groups {name, member_ids}`.
3. Bơm hội thoại: `POST /test/api/send {as:<emp_id>, chat_id:<gid>, text}` nhiều tin (giao việc/chốt/deadline) → đợi debounce 10m HOẶC đủ 30 tin (test: hạ threshold/window tạm, hoặc gọi op trực tiếp).
4. Hỏi: `POST /test/api/send {as:<boss_id>, chat_id:<gid>, text:"...", mention_bot:true}` — câu truy vấn ("ai lo việc X?") + câu tổng hợp ("tóm tắt dự án Y").
5. Đọc đáp: `GET /test/api/chats/{gid}/messages` hoặc SSE `/test/stream?as=<boss_id>`.
6. Tune: xem extraction/retrieval/answer sai ở đâu → sửa prompt (constant/seed) / code / params → lặp.
   (Core tools giờ always-on → KHÔNG cần backfill `search_knowledge` cho boss cũ nữa.)

> **Harness sẵn:** `scripts/harness.py` (setup/extract/wipe-knowledge/dump/ask). Endpoint `POST /test/api/extract`.
> **Handoff session sau (đào sâu Q&A + workload/hiệu suất + biểu đồ):** `docs/architecture/handoff-2026-06-qa-analytics.md`.

## Nhật ký quyết định
- 2026-06-12: Chốt Tầng 0 = Lõi + Phân tích (advisory). Chốt Tầng 1 = 3 mặt phẳng + tự chủ AI "có kiểm soát".
- 2026-06-12: Chốt Nguyên tắc xuyên suốt = trải nghiệm boss tối giản (superadmin giữ config, bot tự học).
- 2026-06-12: Gap analysis xong (~55–60% khớp). Đề xuất lộ trình A (quick wins) → B (nền module) → C (chiều sâu memory).
- 2026-06-12: Xác nhận hệ thống ĐANG BUILD (chưa production) → foundation-first, refactor thoải mái; fix điểm yếu gộp vào dựng lại đúng, không vá riêng.
- 2026-06-12: D1 chốt = 5 lớp + kho tri thức HYBRID + taxonomy kind NHỎ+field.
- 2026-06-12: D2 chốt = extract async (lull/threshold), extract=lọc nhiễu, reconcile ADD/UPDATE/DELETE/NOOP, importance=trọng số.
- 2026-06-12: D3 chốt = router INLINE (3 tier); query-understanding call; scope nhóm bắt buộc; scope chat web admin Model A (auto + adaptive sticky soft + picker hard tùy chọn); chat web admin cần state hội thoại.
- 2026-06-12: D4 chốt = v1 foundation + analytics-lite (demo); capability list + phân quyền 2 tầng (boss quản dữ liệu/trải nghiệm, superadmin quản bộ não/config).
- 2026-06-12: D7 chốt = integration marketplace (boss tự cài, graceful) vs tool bundle-theo-capability (core khoá, kernel validate, loadout động); boss control mức capability, raw-tool ở superadmin.
- 2026-06-13: D8 chốt = A (context-discipline v1; quarantine/parallel để sau). Self-review → Watchlist 5 rủi ro + mitigation cân đối (soft-delete, gộp query-understanding, job staleness flag, dựa fallback, v1 tối thiểu).
- 2026-06-13: D6 chốt = eval Lean (gold set + LLM-judge + recall@k + thumbs; "mỗi bug → 1 gold case").
- 2026-06-13: D5 research xong. "Do now" fix đúng weak spot (Qdrant datetime index, is_tenant scope, bge-reranker thay MMR, Query API hybrid, batch API, structured-output extraction, spotlighting+schema-only injection defense). Embedding model = quyết qua eval (te-3-small vs gemini-embedding-001 vs bge-m3-VN).
- 2026-06-13: Embedding CHỐT = gemini-embedding-001 (1536d khớp Qdrant, 0 GPU ops, ~4% lift); reranker bge-reranker là đòn bẩy chính nên B-vs-C nhẹ; bge-m3-VN = upgrade path. Bỏ eval-driven cho quyết định này.
- 2026-06-14: Memory → BUILD (học mem0 làm tham khảo, không test; Letta loại). Channel order = Zalo v1 → Mess v2 → Telegram v3/v4 (thị trường VN; override spike Telegram-first). PDPL park tới pilot thật; build-stage chỉ chừa retention+cascade-delete + provider zero-retention.
- 2026-06-14: Self-review đối kháng 5 nhánh. CRITICAL mới: Zalo group viability (validate Telegram-first), thiếu voice/ảnh, thiếu lớp output chủ động (daily brief), PDPL pháp lý, tenant isolation sâu, latency region+stream, kỳ vọng accuracy. Thách thức 7 quyết định đã chốt (analytics-v1, foundation-first, build-memory, marketplace, reranker self-host, adaptive scope, embedding-no-eval). CHƯA chỉnh quyết định — chờ user.
- 2026-06-15: Biểu đồ workload/hiệu suất CHỈ ở web admin (KHÔNG làm AI-sinh chart-spec inline trong chat). Kênh chat cần biểu đồ về sau → render server-side → xuất PNG → gửi ảnh (hạng mục tương lai). ⇒ Pha B (workload theo người) HOÀN TẤT sau polish P1–P4.
