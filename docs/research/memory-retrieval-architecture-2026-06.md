# Nghiên cứu: Kiến trúc Memory / Note / Retrieval cho bot thư ký nhóm chat (06/2026)

> Tổng hợp từ: (1) deep-research workflow đa nguồn có kiểm chứng đối kháng, (2) hai nhánh research bổ sung
> (token/latent memory; agentic memory + context engineering), (3) khảo sát toàn bộ codebase hiện tại.
> Mục tiêu: trả lời "dự án nên tiếp cận theo hướng nào" cho 4 vấn đề: note không tối ưu, retrieval sai,
> retrieval chậm, context nhảy lộn xộn.

---

## 1. Kết luận tổng (TL;DR)

Mô hình mà toàn ngành hội tụ năm 2025–2026 (OpenAI Dreaming, Claude Code auto-memory, Letta sleep-time,
Mem0) là **một mô hình duy nhất, ba đường (path)**:

1. **Write path (ingest):** trích xuất theo *cửa sổ hội thoại + summary đang chạy* (không chấm điểm từng
   tin nhắn) → note **có kiểu** (task/decision/fact/deadline/FYI) kèm provenance (ID tin nhắn gốc),
   importance, confidence → **đối chiếu với note đã có** bằng LLM quyết định ADD/UPDATE/DELETE/NOOP.
2. **Sleep path (curation nền):** job định kỳ mỗi nhóm — chuẩn hóa ngày tương đối → tuyệt đối, gộp trùng,
   đóng task xong, loại mâu thuẫn, **viết lại group index ≤200 dòng** (luôn được nạp vào context).
3. **Read path (trả lời):** một agent duy nhất, được nạp sẵn group index, có 3–4 tool search
   (FTS + vector + đọc nguồn), **tự lặp 2–6 tool call**; tool trả kết quả gọn (1 dòng + ID) có tool mở rộng.

Điểm mấu chốt: **chuyển chi phí thông minh từ lúc trả lời (read) sang lúc ghi (write) và lúc rảnh (sleep)**.
Đó là cách đồng thời giải cả 4 vấn đề: note có cấu trúc + tự dọn dẹp; retrieval chính xác hơn vì tìm trên
note đã chưng cất (vẫn giữ raw messages làm lớp 2); nhanh hơn vì phần lớn câu hỏi trả lời được từ index +
note; context sạch vì chỉ nạp thứ liên quan.

Hệ thống hiện tại **đã đúng khung** (pipeline stages, hybrid BM25+vector, note theo nhóm, memory 3 scope) —
không cần đập đi. Vấn đề nằm ở ~8 mắt xích cụ thể, liệt kê ở mục 4.

---

## 2. Bản đồ các hướng tiếp cận + bằng chứng

### 2.1. Memory dạng text có curation nền (HƯỚNG CHÍNH — production-proven)

- **OpenAI Dreaming** (ship 4/6/2026, đã kiểm chứng 3-0 từ nguồn gốc openai.com): tiến trình nền đọc nhiều
  hội thoại, tổng hợp memory state, **tự sửa theo thời gian** ("sẽ đi Singapore tháng 7" → "đã đi Singapore
  7/2026"). Đã chạy hybrid (dreaming + saved memories) ~1 năm trước khi standalone. Bài học: background
  batch curation thắng per-message decision ở quy mô lớn nhất ngành.
- **Claude Code auto-memory + auto-dream**: index ≤200 dòng luôn nạp + file chi tiết đọc theo nhu cầu +
  consolidation nền (chuẩn hóa ngày, xóa fact bị mâu thuẫn, gộp trùng). Template sạch nhất cho quy mô nhỏ.
- **Letta/MemGPT + sleep-time compute** (arXiv 2504.13171): agent nền viết lại context lúc rảnh →
  **~5x giảm compute lúc trả lời**, +13–18% accuracy, 2.5x rẻ hơn khi amortize. MemFS: memory = thư mục
  markdown, agent grep/search — đạt 74.0% LoCoMo với GPT-4o-mini, thắng các memory product chuyên dụng.
- **Mem0** (arXiv 2504.19413): 2 phase — *extraction* (LLM + summary đang chạy + N tin nhắn cuối → fact
  ứng viên; chính extraction là bộ lọc nhiễu) và *update* (so với memory tương tự, LLM chọn
  ADD/UPDATE/DELETE/NOOP). Tự nhận 91% giảm p95 latency, >90% tiết kiệm token so với full-context.
  ⚠️ Số trên LoCoMo bị Zep phản bác (benchmark yếu, đối thủ bị cấu hình sai) — coi là chỉ dấu, không phải chân lý.
- **Zep/Graphiti**: temporal knowledge graph, fact có validity window. Claim "thắng MemGPT trên DMR" **bị
  bác khi kiểm chứng (0-2)** — đừng dùng số này để ra quyết định. Có độ trễ ingest (fact chỉ xuất hiện sau
  khi graph xử lý nền xong). Với quy mô hiện tại của dự án: KG là overkill, chưa cần.
- **LangMem (LangChain)**: phân biệt **profile** (1 document theo schema, update-in-place — hợp với
  "trạng thái hiện tại": task status, thông tin nhóm) vs **collection** (record rời, append — bắt buộc
  có bước reconciliation, nếu không sẽ tích mâu thuẫn). Hot-path memory (ghi ngay, thêm latency) vs
  background (không thêm latency, trễ một chút) — background là mặc định đúng cho chat bot.

### 2.2. Trích xuất có cấu trúc vs raw text — và giới hạn của extraction

- arXiv 2603.04814 (chưa kiểm chứng phiếu do hết quota, nguồn primary): fact-based memory **thua**
  long-context model về recall thuần (57.68% vs 92.85% LoCoMo với GPT-5-mini); extraction **lossy có quy
  luật**: mất mốc thời gian chính xác, mất coreference ("cái đó", "anh ấy"), mất chi tiết one-off.
  Fact memory chỉ rẻ hơn sau ~10 lượt hỏi trên cùng context.
- Hệ quả thiết kế: **note chưng cất là lớp 1, raw messages phải giữ lại làm lớp 2** (đã có sẵn trong
  hệ thống — bảng `messages` + FTS + Qdrant). Mọi note phải có provenance trỏ về tin nhắn gốc để agent
  đọc lại khi cần chi tiết.

### 2.3. Retrieval: one-shot pipeline vs agentic search

- HERB benchmark (arXiv 2506.23139, dữ liệu Slack + transcript + docs — đúng domain của mình): agentic
  ReAct 32.96 vs hybrid one-shot 20.61; **retrieval là nút cổ chai, không phải reasoning** (Gemini-2.5-Flash:
  76.55 full-context vs 41.86 sau retriever). Cả hai số còn thấp → bài toán chưa ai giải trọn.
- "Is Grep All You Need?" (arXiv 2605.15184, LongMemEval — QA trên lịch sử chat): grep thắng vector ở mọi
  cặp model khi tool trả inline (93.1% vs 83.6%), **nhưng đảo chiều tùy harness** (có cặp grep sụp
  93.1%→55.2%). Kết luận: không có "vector mặc định" hay "grep mặc định" — **hybrid + thiết kế harness +
  cho agent lặp** mới là biến số quyết định.
- Claude Code bỏ vector RAG dùng glob+grep+read; Augment/SWE-bench: "embedding không phải bottleneck" vì
  agent tự sửa hướng qua nhiều lượt. Nuance của chính họ: **expose embedding search như một tool trong
  agentic loop** — đúng thiết kế nên theo. Tiếng Việt group chat là dạng unstructured content mà
  lexical-only yếu nhất → giữ Qdrant, thêm khả năng lặp.
- Chi phí: agentic search = 2–6 LLM round-trip → giây chứ không phải ms. Bù bằng: phần lớn câu hỏi trả
  lời từ group index + notes (không cần search), chỉ câu khó mới vào loop.

### 2.4. Context engineering (giải thích trực tiếp "context nhảy lộn xộn")

- **Context rot** (Chroma, 18 model): chất lượng suy giảm từ rất lâu trước giới hạn window (có thể từ
  ~50k/200k); **distractor** — nội dung cùng chủ đề nhưng cũ/sai — là thứ giết accuracy mạnh nhất.
  Tin nhắn cũ cùng topic trong group chat chính là distractor giáo khoa. LongMemEval: prompt ~300 token
  tập trung thắng áp đảo prompt ~113k token chứa cả đáp án.
- **Anthropic context engineering**: JIT retrieval (giữ ID/reference, load qua tool khi cần) > preload;
  hybrid như Claude Code (preload CLAUDE.md, grep phần còn lại); tool result phải phân trang/cắt
  (Claude Code cap 25k token/tool result); subagent trả digest 1.000–2.000 token; tool ít và không
  chồng lấn. Context editing (xóa tool result cũ): +29% trên agentic search, -84% token.
- **Slack AI** (nguồn primary slack.com): stateless RAG, không train trên dữ liệu khách; **ACL enforce
  lúc fetch, không phải lúc generate** — pattern bắt buộc cho bot nhiều nhóm/nhiều user.

### 2.5. Multi-agent

- Anthropic (orchestrator-worker, thắng single-agent 90.2% trên research): chỉ đáng cho việc ĐỌC
  song song giá trị cao; tốn ~15x token. Cognition ("Don't build multi-agents"): agent song song tự
  quyết định ngầm mâu thuẫn nhau → output bất nhất; khuyên single-thread + compressor.
- Hòa giải (LangChain): **multi-agent OK cho READ, hỏng cho WRITE**. Thiết kế đúng cho bot mình:
  **các pipeline stage chia sẻ state qua Postgres** (curator ghi note — một writer duy nhất/nhóm;
  consolidator chạy cron; responder trả lời) — KHÔNG phải agents nhắn tin cho nhau. Subagent-as-tool
  (retrieval subagent trả digest 1–2k token) chỉ thêm khi đo thấy context responder bị bẩn.

### 2.6. "Lưu memory bằng token thuần" (KV-cache/latent) — kết luận dứt khoát

- Cartridges (Stanford, KV cache huấn luyện: 38.6x ít memory, 26.4x throughput), Titans/Hope (Google),
  MemoryLLM, gist tokens/ICAE, LMCache, C2C: **tất cả đòi sở hữu weights + tự host inference**.
  Không provider hosted nào cho upload/giữ KV cache riêng. → KHÔNG áp dụng được cho dự án (đang gọi API).
- Thứ dùng được ở tầng API: **prompt caching** (Claude ~90% off phần cache đọc, OpenAI 50–90%, Gemini có
  explicit CachedContent API trả phí theo token-giờ) + **precomputed text memory**. Combo này lấy ~90%
  lợi ích thực tế. Code đã có `cache_prefix_hint` — việc cần làm là xếp layout prompt: phần ổn định
  (system → group index → memory) lên đầu, phần biến động (retrieval, câu hỏi) xuống cuối.
- LLMLingua (nén prompt client-side, output vẫn là text): chỉ đáng cho context không cache được
  (retrieval chunks dài). Ưu tiên thấp.

---

## 3. Đối chiếu hiện trạng code → nguyên nhân gốc của 4 vấn đề

| Vấn đề | Nguyên nhân trong code | Bằng chứng nghiên cứu liên quan |
|---|---|---|
| Note không tối ưu | Note = 1 blob markdown, LLM viết lại toàn bộ mỗi 10ph/30 msg (`note_service.py`); `memory_entries` upsert **ghi đè toàn phần theo key**, mất lịch sử | LangMem: collection cần reconciliation; Mem0 update-phase; Dreaming: silent rewrite là anti-pattern khi không có version |
| Retrieval sai | Lọc thời gian **sau** Qdrant top-30 (`dense.py` — có thể trả 0 hit); MMR dùng Jaccard từ vựng (`mmr.py`); không rerank ngữ nghĩa; không query rewriting; search trên raw messages, chưa index notes | HERB: one-shot 20.61 vs agentic 32.96; LongMemEval-grep: harness quyết định; 2603.04814: extraction lossy → cần cả 2 lớp |
| Chậm | Tool call tuần tự trong agent loop; embed mỗi query; mọi câu hỏi đều qua search pipeline | Sleep-time: 5x; Mem0: 91% p95; trả lời từ index không cần search |
| Context lộn xộn | Top-20 semantic memory **luôn** inject bất kể câu hỏi (`agent_loop.py:162-188`); `chat_id` optional → trộn nhóm; không có conversation state; hit thô nhồi vào prompt | Chroma context rot: distractor + always-inject là thủ phạm; Slack AI: scope lúc fetch; Anthropic: JIT + cap tool result |

---

## 4. Khuyến nghị kiến trúc — lộ trình ưu tiên

### P0 — Sửa lỗi sai trực tiếp (vài ngày, không đổi schema)

1. **Scope retrieval theo nhóm mặc định**: `chat_id` bắt buộc trong `search_history` trừ khi user hỏi
   xuyên nhóm một cách tường minh; lọc thêm theo quyền người hỏi (pattern Slack AI).
2. **Sửa lọc thời gian**: đưa `ts` (epoch) vào Qdrant payload + payload index, filter range ngay trong
   query Qdrant thay vì hậu kỳ SQL; hoặc tối thiểu oversample (k=100) khi có time filter.
3. **Bỏ inject top-20 semantic mặc định** → chỉ inject group index (khi có) + top-3..5 memory thực sự
   liên quan câu hỏi (threshold theo similarity, không phải fixed-k).
4. **Cap & định dạng tool result**: search trả ≤10 hit dạng 1 dòng + message_id; thêm tool
   `read_messages(ids/window)` để agent mở rộng — JIT retrieval đúng nghĩa.

### P1 — Tái cấu trúc note/memory (1–2 tuần)

5. **Bảng notes có kiểu** (thay/đặt cạnh blob markdown): `kind` (task/decision/fact/deadline/fyi),
   `content`, `importance` (LLM chấm 1–10 lúc ghi — trọng số xếp hạng, KHÔNG phải ngưỡng xóa),
   `confidence`, `source_message_ids[]` (provenance), `status`, `valid_from/valid_to`, embedding → Qdrant.
   Blob markdown hiện tại trở thành **view render từ notes** thay vì source of truth.
6. **Write path kiểu Mem0**: giữ debounce hiện có (10ph/30msg là một dạng lull-trigger tốt) nhưng đổi
   việc làm: thay vì viết lại blob → extract note ứng viên từ (summary nhóm + delta messages) → fetch
   top-k note tương tự từ Qdrant → LLM quyết ADD/UPDATE/DELETE/NOOP. Mỗi mutation ghi vào bảng
   `note_revisions` (audit trail — học từ chính bài Dreaming: không silent rewrite).
7. **Group index ≤200 dòng** (kiểu Claude Code MEMORY.md): fact chủ chốt, người, dự án đang chạy, task
   mở, deadline gần — luôn nạp vào prompt responder, đặt **đầu prompt** (sau system), nằm trong vùng
   prompt cache.
8. **Nightly dreaming job** mỗi nhóm active: chuẩn hóa ngày tương đối → tuyệt đối, gộp note trùng
   (semantic, không phải Jaccard), đóng task đã xong, hạ importance note hết hạn, viết lại group index.
   Model rẻ cho extraction hằng ngày, model tốt cho consolidation đêm (pattern Letta asymmetric).

### P2 — Nâng chất lượng read path

9. **Agentic retrieval đúng nghĩa**: responder lặp tối đa 4–6 tool call với loadout nhỏ:
   `search_notes` (FTS+vector trên notes), `search_messages` (pipeline hiện có), `read_messages`,
   `list_tasks`. Câu dễ: trả lời thẳng từ index, 0 tool call. Bỏ MMR-Jaccard, thay bằng rerank ngữ nghĩa
   (embedding-MMR hoặc LLM rerank nhẹ) — chỉ khi đo thấy cần.
10. **Prompt cache layout**: prefix ổn định (system → group index → memory block) + volatile cuối;
    đo cache-hit-rate. Đã có `cache_prefix_hint`, chỉ cần sắp xếp lại thứ tự khối.
11. **Eval trước khi tinh chỉnh tiếp**: bộ ~50 câu hỏi thật từ nhóm thật + LLM-as-judge; mọi thay đổi
    P1/P2 phải đo trên bộ này. (Bài học Anthropic multi-agent: outcome-based eval là hạ tầng bắt buộc.)

### KHÔNG làm (bây giờ)

- Temporal knowledge graph (Zep/Graphiti): overkill ở quy mô hiện tại, thêm độ trễ ingest; số liệu
  quảng cáo không qua được kiểm chứng.
- Multi-agent mesh / retrieval subagent: chỉ cân nhắc khi eval cho thấy context responder bị bẩn.
- KV-cache/latent memory, LLMLingua: không áp dụng được hoặc ROI thấp khi đang dùng hosted API.
- Thay Qdrant bằng pgvector hay ngược lại: không phải bottleneck; giữ nguyên.

---

## 5. Anti-patterns cần tránh (rút từ chính bài Dreaming + nghiên cứu)

1. **Silent rewrite không audit trail**: mọi mutation note/memory phải có revision log + provenance.
   (`memory_entries` upsert hiện tại đang vi phạm.)
2. **Prompt injection vào memory**: nội dung tin nhắn nhóm là untrusted input; tách rõ khối DATA vs
   INSTRUCTION trong prompt extraction/responder; không bao giờ để nội dung retrieved được diễn giải
   như lệnh hệ thống. (Tenable đã chứng minh vector này trên ChatGPT memory.)
3. **Importance làm ngưỡng xóa cứng**: importance chỉ là trọng số xếp hạng (Generative Agents);
   note importance thấp vẫn phải surface được khi relevance cao.
4. **Nhồi raw history vào prompt**: distractor giết accuracy (Chroma); luôn đi qua lớp lọc/chưng cất.
5. **Tin số benchmark của vendor**: Mem0 vs Zep vs Letta đều tự công bố số có lợi cho mình trên LoCoMo —
   benchmark này yếu (hội thoại chỉ 16–26k token). Tự đo trên eval của mình là bắt buộc.

---

## 6. Ghi chú độ tin cậy

- **Đã kiểm chứng đối kháng 3-0 / 2-0 từ nguồn gốc**: 3 claim về cơ chế Dreaming (background process,
  temporal revision, hybrid 1 năm).
- **Bị bác (0-2)**: "Zep thắng MemGPT trên DMR 94.8% vs 93.4%".
- **Chưa qua vòng phiếu do hết quota giữa chừng** (nguồn primary, nhiều claim được nhánh research thứ 2
  kiểm chứng chéo độc lập): HERB benchmark, Mem0 numbers, 2603.04814, LangMem concepts, Slack AI,
  context rot, JIT retrieval. Các con số cụ thể trong nhóm này nên coi là chỉ dấu định hướng.

## 7. Nguồn chính

- openai.com/index/chatgpt-memory-dreaming · anthropic.com/engineering/effective-context-engineering-for-ai-agents
- anthropic.com/engineering/multi-agent-research-system · anthropic.com/engineering/writing-tools-for-agents
- claude.com/blog/context-management · code.claude.com/docs/en/memory · platform.claude.com/docs (memory tool)
- cognition.ai/blog/dont-build-multi-agents · trychroma.com/research/context-rot
- letta.com/blog/benchmarking-ai-agent-memory · letta.com/blog/sleep-time-compute · arXiv 2504.13171
- arXiv 2504.19413 (Mem0) · blog.getzep.com (Mem0 rebuttal) · arXiv 2501.13956 (Zep)
- arXiv 2506.23139 (HERB) · arXiv 2605.15184 (Is Grep All You Need) · arXiv 2603.04814 (fact vs full-context)
- arXiv 2304.03442 (Generative Agents) · github.com/langchain-ai/langmem (conceptual guide)
- slack.com/blog/news/how-we-built-slack-ai-to-be-secure-and-private
- arXiv 2506.06266 (Cartridges) · arXiv 2501.00663 (Titans) · microsoft.com/research (LLMLingua)
- dbreunig.com (context failure taxonomy) · langchain.com/blog/how-and-when-to-build-multi-agent-systems
