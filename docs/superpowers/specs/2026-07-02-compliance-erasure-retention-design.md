# Design — Compliance: cascade-delete thật + retention TTL tin nhắn thô

> Spec gọn (cùng đợt với zalo-automation; consent notice đã xong ở spec đó).
> PDPL yêu cầu 2 thứ code phải LÀM THẬT: quyền xoá dữ liệu (erasure) và
> không giữ tin nhắn thô vô hạn (retention). Design 06-14 mới "chừa đường".

## 1. Hiện trạng (khảo sát 2026-07-02)

- `DELETE /groups/{id}` chỉ xoá row `group_notes` — messages/knowledge/qdrant
  của nhóm VẪN NẰM LẠI (retrieval vẫn trả lời từ nhóm "đã xoá").
- Không có code retention/purge nào. FK từ bảng boss-scoped → users phần lớn
  NO ACTION (xoá boss = lỗi FK).
- Sẵn có để dựa vào: con của `group_notes` (pins/action_items/members/
  versions/summaries/decisions/artifacts) đều ON DELETE CASCADE;
  `knowledge_provenance`/`revisions` CASCADE theo knowledge_items;
  `knowledge_provenance.message_id` CASCADE theo messages (xoá tin thô không
  gãy); Qdrant payload có `boss_id`+`chat_id`+`kind` → filter-delete được.

## 2. Thiết kế

### 2.1 `DataErasure` service (`src/services/data_erasure.py`)

- `erase_group(boss_id, provider, chat_id) -> dict[str,int]` — xoá theo nhóm,
  boss-scoped: qdrant points (boss+chat, kind=knowledge) → knowledge_items →
  messages → outbound_messages → scheduled_reminders (chat) → group_notes
  (children cascade). Trả counts để audit/hiển thị.
- `erase_boss(boss_id) -> dict[str,int]` — right-to-erasure toàn bộ:
  qdrant (mọi kind theo boss_id) + mọi bảng boss-scoped theo thứ tự FK-safe
  (group_notes sớm để cascade con; assignments trước bot_accounts;
  bot_accounts boss_owned; web identity: web_users theo boss_user_id —
  web_group_members cascade). **Users row KHÔNG xoá mà ANONYMIZE** (email →
  `erased-<id>@erased.invalid`, name/password/google_sub/api_keys NULL) —
  giữ FK integrity cho audit_log/billing, vẫn đạt mục tiêu xoá dữ liệu cá nhân.

### 2.2 Đấu dây

- `DELETE /api/v1/admin/groups/{id}` → gọi `erase_group` (UI "Xoá nhóm" giờ
  xoá THẬT dữ liệu nhóm). Semantic change có chủ đích — build stage.
- Superadmin: `POST /api/v1/superadmin/bosses/{boss_id}/erase` → `erase_boss`
  + admin_audit_log (action `boss.data_erased`, payload counts). Không làm FE
  đợt này (thao tác hiếm, gọi API/curl được; nút UI khi cần).

### 2.3 Retention job (`src/scheduler/jobs/raw_message_retention.py`)

- Setting `RAW_MESSAGE_RETENTION_DAYS` (mặc định **180**; `0` = tắt).
- Job chạy mỗi 24h (đăng ký trong `scheduler/runner.py` như reverify):
  xoá `messages` + `outbound_messages` có `ts/created_at` quá hạn, batch 5000
  mỗi vòng tránh lock dài. Spine knowledge KHÔNG đụng — tri thức đã chưng cất
  giữ lại, tin thô (nhạy nhất) mới bị dọn. Provenance mất theo tin (cascade)
  = chấp nhận, knowledge content còn nguyên.

## 3. Non-goals

- Self-service "xoá dữ liệu của tôi" cho THÀNH VIÊN nhóm (không phải boss):
  khi có yêu cầu thật → superadmin xử lý thủ công bằng erase-API + SQL theo
  sender_provider_id; tự động hoá để sau.
- Retention theo từng boss/gói (per-boss override) — platform-level trước.
- Backup/soft-delete/undo — erasure là erasure.

## 4. Definition of done

- Integration tests: erase_group sạch đúng scope (nhóm khác/boss khác còn
  nguyên), erase_boss sạch mọi bảng + users anonymized; retention xoá đúng
  tin cũ, giữ tin mới, `0` = không xoá gì.
- Full pytest xanh; gold/multipass/workload/zalo không regress (đường bot
  không đổi — chỉ thêm service/job/endpoint).
