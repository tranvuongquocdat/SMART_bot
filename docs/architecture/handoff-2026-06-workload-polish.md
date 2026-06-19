# HANDOFF — Phiên sau: POLISH lớp workload / "Hiệu suất" (Pha B)

> Pha A (Q&A) + Pha B (workload theo người, spine làm nguồn + trang admin Hiệu suất) ĐÃ XONG và
> **đã merge `main`** (PR #4, merge commit `8b3c5b9`). Phiên này CHỈ polish lớp workload vừa làm.
> Chi tiết kiến trúc + nhật ký ở `docs/architecture/system-design.md` (BUILD LOG, các mục 2026-06-15).

## 0. Trạng thái
- Spine LIVE trên gpt-5.4-mini. Workload chạy e2e: `knowledge_items` có `assignee_name`+`due_at`
  (extract điền) → `KnowledgeRepo.workload_summary` → tool `workload_summary` (bot trả lời) +
  endpoint `GET /api/v1/admin/workload` → trang admin `/app/admin/performance`.
- **Regression XANH** (chạy lại đầu phiên để chắc nền): `gold` 11/11 · `multipass` 6/6 · `workload` 4/4.
- ⚠️ Trên `main` còn **WIP admin AI-settings chưa commit** (ai-tab, own-model-drawer, boss_ai_config,
  config.py, api_ai, 6 hunk trong api_admin.py, migration 0014, mockups/) — KHÔNG đụng, KHÔNG commit kèm.

## 1. Setup (như cũ)
```bash
bash scripts/restart.sh   # hoặc: ENABLE_WEB_TEST_CHANNEL=true uv run uvicorn src.main:app --port 8000
bash scripts/seed_llm.sh && uv run python scripts/seed_prompts.py
```
PG `localhost:5433` smart/smart/smart_bot · Qdrant `localhost:6333`. Harness: `scripts/harness.py`
(`setup` tạo Apollo+Beta tái lập · `extract` · `gold`/`multipass`/`workload` regression · `ask "<q>"`).
⚠️ Soi DB phải lấy boss từ `/tmp/harness_state.json` — id boss/nhóm là hex NGẪU NHIÊN, `ORDER BY id DESC` vô nghĩa.

## ✅ CẬP NHẬT 2026-06-15 — P1–P4 ĐÃ XONG (P5 hoãn theo quyết định user)
- **P1** ✅ chụp UI `/app/admin/performance` — render đúng, khớp endpoint, không viền trắng (dark).
- **P2** ✅ gộp đầu việc/người — EXTRACT **v8** ("GỘP THEO ĐẦU VIỆC": phân-công + deadline/ước lượng/tiến
  độ cùng việc → 1 mục, due gắn vào mục đó VÀ nêu hạn trong content; deadline CHUNG dự án vẫn riêng). Over-count
  trên Apollo: An 3→2, Bình 3→2 (tổng mở 9→7). +2 check trong `harness.py workload` (kịch bản Zeta).
- **P3** ✅ tool `list_members` (`GroupNotesRepo.list_members` provider-agnostic + tool ở `meta.py`, đăng ký
  dm+in_group). Bot trả roster + "ai rảnh" (gộp với workload_summary). KÈM responder **v6** (dm+in_group): hướng
  dẫn list_members + chốt "deadline sắp tới/gần nhất = mốc TƯƠNG LAI gần nhất" (trị flaky `cross-nearest-deadline-dm`).
  (LƯU Ý: handoff nhắc "nudge prompt" nhưng KHÔNG có agent nudge trong codebase → bỏ qua.)
- **P4** ✅ bộ lọc nhóm — `GET /admin/groups` thêm `chat_id` + `name` COALESCE `web_groups.name`; FE Select
  "Tất cả nhóm"/từng nhóm → `workloadQuery(chat_id)` + Suspense cục bộ; i18n vi/en. Chụp UI: filter chạy thật.
- **Regression cuối phiên:** gold 11/11 · multipass 6/6 · workload 6/6. BUILD LOG chi tiết ở `system-design.md`
  (3 mục "PHA B POLISH P1+P2 / P3 / P4", 2026-06-15). Thay đổi CHƯA commit (chờ lệnh); KHÔNG đụng WIP AI-settings.
- **P5 = BỎ (user chốt 2026-06-15):** KHÔNG làm AI-sinh chart-spec inline. Chart chỉ cần ở web admin (đã có).
  Kênh chat về sau, nếu cần biểu đồ → render server-side → xuất PNG → gửi ảnh (hạng mục tương lai riêng).
  ⇒ Pha B (workload/Hiệu suất) coi như HOÀN TẤT. Xem chi tiết ở mục P5 bên dưới + Nhật ký quyết định.

## 2. Việc polish (ưu tiên giảm dần)

### P1. Chụp ảnh UI trang "Hiệu suất" (xác nhận nhanh, làm trước)
Mới chỉ verify endpoint (200 + data đúng) + FE build sạch, CHƯA xem render thật. Đăng nhập boss
(mint cookie qua `src.web.security.make_session(boss_id)` — xem `/tmp/probe_endpoint.py` mẫu) →
mở `/app/admin/performance` → chụp ảnh. Kiểm RankBars + bảng quá hạn + summary card hiển thị đúng,
không vỡ layout/viền trắng (dark mode).

### P2. Gộp item "phân công" + "deadline" cùng người (đếm hơi dư)
Hiện extract đôi khi tách "Phân công backend cho An" (assignee=An) + "Dời deadline backend" (assignee=An,
due=10/7) thành 2 item → An bị đếm 2 việc cho cùng 1 đầu việc backend → workload phồng.
- Hướng: tune EXTRACT (prompt `config/seeds/prompts/knowledge_extract.yaml` + constant trong
  `src/services/knowledge_service.py`) — khi một deadline GẮN với một phân công đã nêu trong cùng đoạn,
  GỘP `due` vào item phân công đó thay vì tạo item riêng. (Bump version prompt, reseed.)
- Verify: thêm 1 check vào `harness.py workload` hoặc 1 scenario: An chỉ đếm đúng số đầu việc thật.
- Lưu ý đừng phá `gold`/`multipass` (deadline-change cross-batch vẫn phải UPDATE đúng).

### P3. `list_members` tool (roster / "ai đang rảnh")
workload_summary chỉ thấy người CÓ việc; "ai rảnh / đủ người team" cần roster đầy đủ.
- Members ở `group_members` (kênh thật) / `web_group_members` (test) = (group_id, user_id) → join tên.
  Cross-provider hơi rườm (xem `list_groups` trong `src/tools/core/meta.py` dùng `group_notes` provider-agnostic).
- Thêm tool `src/tools/core/` + đăng ký vào `tools={...}` của in_group + dm responder + nudge prompt.

### P4. Bộ lọc nhóm trên trang Hiệu suất
Endpoint `GET /api/v1/admin/workload` ĐÃ nhận `group_id`. FE chỉ cần thêm dropdown chọn nhóm
(lấy list nhóm — cân nhắc endpoint admin groups sẵn có, hoặc thêm) → `workloadQuery(group_id)`.
Files: `frontend/src/modules/admin/features/performance/{page,api}.tsx` + i18n.

### P5. ❌ BỎ — KHÔNG làm AI-sinh chart-spec inline (user chốt 2026-06-15)
**Quyết định mới (thay hướng cũ):** chart CHỈ cần ở **bản web admin** (đã xong qua P1/P4 — RankBars + bảng +
summary card). KHÔNG đi hướng "AI tự sinh chart-spec để vẽ inline trong chat". Kênh chat (Zalo, …) phần lớn
KHÔNG render được chart phong phú → khi cần biểu đồ trong chat sẽ làm theo hướng **render chart server-side →
xuất PNG → gửi như ẢNH đính kèm** (handle sau, không phải LLM sinh spec). ⇒ Pha B coi như HOÀN TẤT ở mức cần
thiết; việc "chart-as-image cho kênh chat" là hạng mục TƯƠNG LAI riêng, không thuộc polish này.

## 3. PROMPT paste cho phiên mới
```
Đọc docs/architecture/handoff-2026-06-workload-polish.md (+ BUILD LOG trong system-design.md,
mục 2026-06-15). Pha A + B đã merge main. Phiên này POLISH lớp workload/Hiệu suất theo thứ tự P1→P5
trong handoff: (P1) chụp ảnh UI trang /app/admin/performance xác nhận render; (P2) gộp item phân-công+
deadline cùng người để workload khỏi đếm dư; (P3) tool list_members (roster/ai rảnh); (P4) bộ lọc nhóm
trên trang Hiệu suất; (P5 tùy chọn) AI-sinh chart-spec. Chạy regression gold/multipass/workload đầu phiên
để chắc nền, mỗi thay đổi verify lại + giữ 3 bộ xanh. KHÔNG đụng WIP admin AI-settings chưa commit. Báo từng vòng.
```
