# HANDOFF — Session sau: đào sâu Q&A + hướng workload/hiệu suất + biểu đồ

> Mục tiêu user cho session mới: **tối ưu KỸ phần hỏi-đáp bình thường trước**, rồi mở sang
> câu hỏi **quản lý workload / check hiệu suất team** (AI tự đi lấy team → member → task →
> tổng hợp), và **tạo biểu đồ từ template** để đưa cho admin. CHƯA đẩy mạnh output chủ động.

## 0. Trạng thái hiện tại (đọc kèm BUILD LOG trong `system-design.md`)
Spine knowledge LIVE trên **gpt-5.4-mini** (smart default; llama fallback). Đã verify e2e:
extract (recall cao) · reconcile ADD/UPDATE/DELETE · retrieval hybrid + **scope theo nhóm** ·
responder (search_knowledge-first, không bịa) · core tools **always-on cho mọi boss**. Chi tiết
+ các fix (max_completion_tokens, fallback string/dict, group scoping, core-uncapped) ở BUILD LOG
mục 2026-06-14.

## 1. Setup môi trường (1 lần)
```bash
# infra + migrate + server (cần ENABLE_WEB_TEST_CHANNEL=true)
bash scripts/restart.sh            # hoặc: ENABLE_WEB_TEST_CHANNEL=true uv run uvicorn src.main:app --port 8000
bash scripts/seed_llm.sh           # models/routes/budgets — GỒM gpt-5.4-mini (smart default) + knowledge_*
uv run python scripts/seed_prompts.py   # prompts (bảng rỗng = responder KHÔNG có system prompt!)
```
Postgres: `localhost:5433` user/pass/db = `smart/smart/smart_bot`. Qdrant: `localhost:6333`.
API keys đã có trong `.env` (`PLATFORM_OPENAI_API_KEY` truy cập được gpt-5.4-mini).

## 2. Harness — `scripts/harness.py` (state: `/tmp/harness_state.json`)
Driver test qua kênh web `/test/api/*` + soi DB. Lệnh:
```bash
uv run python scripts/harness.py setup           # tạo boss+3 nhân viên+nhóm "Apollo", gửi hội thoại mẫu
uv run python scripts/harness.py extract          # fire knowledge_extract NGAY (reset cursor) + dump knowledge
uv run python scripts/harness.py wipe-knowledge    # xoá knowledge DB + Qdrant points (sạch để test lại)
uv run python scripts/harness.py dump              # in knowledge_items của boss
uv run python scripts/harness.py ask "<câu hỏi>"   # boss hỏi (mention bot) → in câu trả lời
```
- `POST /test/api/extract {chat_id, reset?}` (đã thêm vào `src/channels/web/routes.py`) fire extraction
  đồng bộ (bus await) — bỏ qua debounce 10m/threshold 30.
- Bus publish await handler ⇒ `/test/api/send` với `mention_bot:true` **block tới khi bot trả xong** →
  đọc đáp ngay qua `/test/api/chats/{gid}/messages`.
- Soi tool AI gọi: bảng `tool_call_log` (tool_name/status/trace_id). Log I/O tool: structlog
  `agent_tool_call`/`agent_tool_result` trong stdout server (đã thêm ở `agent_loop.py`).
- ⚠️ Câu hỏi tag-bot CŨNG được lưu thành message → extract lần sau có thể bắt nhầm; khi test extraction
  sạch thì wipe + gửi hội thoại trước, hỏi sau (extract prompt đã có guard bỏ câu hỏi nhưng không tuyệt đối).

## 3. PHA A — đào sâu Q&A bình thường (TUNE, không build mới) — làm trước
Dùng spine + harness sẵn có. Mở rộng kịch bản (sửa `CONVO`/thêm scenario trong harness) để bắt lỗi:
- Đa nhóm (đã có Beta) + câu hỏi dễ lẫn nhóm; hội thoại DÀI (>30 tin) nhiều dự án.
- Câu mơ hồ / nhiều bước / suy luận thời gian ("việc nào trễ hạn tuần này?").
- Tổng hợp nhiều item; câu không có đáp (phải nói "chưa có thông tin", không bịa).
- Reconcile nhiều pass (đính chính/hủy/hoàn thành) ở quy mô lớn hơn.
Tune: prompt responder `in_group` (DB, sửa qua `seed_prompts.py`/web), prompt extract/reconcile
(CONSTANT trong `src/services/knowledge_service.py`), params. Mỗi bug → 1 gold case (D6).

## 4. PHA B — workload / hiệu suất / biểu đồ (CẦN BUILD, không chỉ tune)
Đây là lớp MỚI, phần lớn CHƯA có. Bản đồ năng lực:

**ĐÃ có:**
- `action_items` (text, `assignee_name` *free-text*, `due_at`, `status='open'|...`, `source`, `project_id`)
  + tool `list_action_items` / `mark_action_item`. → "task" tồn tại.
- `group_members` / `web_group_members` (ai trong nhóm). Nhóm ≈ "team" hiện tại (CHƯA có entity "team" riêng).
- `list_groups`. Knowledge spine cho Q&A phi cấu trúc.

**CHƯA có (cần quyết + build cho mục tiêu):**
1. **Entity người/team**: `assignee_name` là TEXT tự do (people/aliases đã DEFER) → "hiệu suất theo người"
   bị mờ (khớp tên). Quyết: dùng group=team + assignee free-text (lean) hay dựng model people/team.
2. **Tool cho agent "tự đi lấy"**: chưa có `list_members`/`list_team`/`get_tasks_by(assignee|team|status)`.
   Agent loop ĐÃ chain được tool (max_iters=5) — chỉ thiếu tool để fetch/aggregate.
3. **Aggregation workload/hiệu suất**: chưa có tool gộp action_items theo assignee/nhóm/status
   (open/overdue/done, completion rate). Cần 1 tool "workload/perf summary" trên `action_items`.
4. **Biểu đồ từ template**: HIỆN KHÔNG CÓ gì. Responder trả TEXT. Cần quyết:
   - **Surface render**: web admin (render chart component) là chỗ hợp lý cho "đưa cho admin"
     (chat Zalo khó hiển thị chart → có thể gửi ảnh render sau).
   - **Cơ chế**: tool trả **chart-spec** (kiểu {type, title, series}) theo **template** định sẵn
     (bar/line/pie…), FE/endpoint render. Đây là mảnh lớn nhất, nên brainstorm scope trước khi code.

**Đề xuất thứ tự Pha B (core-out):** (a) tool `list_members` + `workload_summary`(aggregate action_items)
→ test câu "team X làm gì, ai quá tải, việc trễ hạn" bằng agent chaining; (b) chốt surface + chart-spec
template + 1 chart đơn (bar completion theo người) render ở web admin; (c) mở rộng template.

## 5. PROMPT để PASTE vào session mới
```
Đọc docs/architecture/handoff-2026-06-qa-analytics.md (và BUILD LOG trong
docs/architecture/system-design.md). Spine knowledge đã LIVE trên gpt-5.4-mini, core tools always-on,
harness ở scripts/harness.py. Mục tiêu session này: (1) ƯU TIÊN đào sâu + tối ưu Q&A BÌNH THƯỜNG cho
thật kỹ (đa nhóm, hội thoại dài, câu mơ hồ/đa bước/suy luận thời gian, tổng hợp, không bịa, reconcile
nhiều pass) — dùng harness, mỗi bug ghi 1 gold case; (2) SAU đó mở sang câu hỏi quản lý workload /
check hiệu suất team: AI tự đi lấy team→member→task→tổng hợp, rồi tạo BIỂU ĐỒ từ template đưa cho admin.
Lưu ý Pha 2 phần lớn CHƯA build (xem "Pha B" trong handoff: thiếu tool list_members/workload_summary +
toàn bộ lớp chart-spec/template/render) → khảo sát rồi đề xuất scope trước khi code, đừng giả định có sẵn.
Làm core-out, lean, verify từng bước qua harness + boss trial mới. Báo từng vòng.
```

## 6. Lưu ý vận hành
- Server đang chạy nền trên :8000 (gpt-5.4-mini). Restart sau khi đổi code Python: kill listener :8000
  rồi `ENABLE_WEB_TEST_CHANNEL=true uv run uvicorn src.main:app --port 8000` (không cần --reload để khỏi
  reload giữa request). FE đổi: `cd frontend && npm run build`.
- Còn nợ (chưa cần gấp): `search_history` (hồi sinh subsystem message-retrieval) · reconcile
  similarity-fetch khi 1 nhóm >50 item.
- gpt-5.4-mini là QUYẾT ĐỊNH TẠM THỜI; gpt-4o vẫn active (không default) để A/B.
