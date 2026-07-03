# Design — Điều khoản (ToS/Privacy) + consent mô hình B

> User chốt qua thảo luận 2026-07-02 (mức B khuyến nghị, user AFK — có thể
> điều chỉnh sau). Hai mảnh: (1) quản lý điều khoản có version + acceptance,
> (2) consent nhóm mô hình B: notice (đã có) + opt-out cá nhân + boss cam kết.

## 1. Quản lý điều khoản

- **Bảng** `legal_documents(kind terms|privacy, version, content_md, published_at, is_active)`
  + `legal_acceptances(user_id, kind, version, accepted_at)`. Publish bản mới =
  insert version mới + deactivate bản cũ (giữ lịch sử).
- **Nội dung**: draft VN ở `config/seeds/legal/{terms,privacy}.md` (khung PDPL;
  luật sư duyệt trước khi thu tiền), seed bằng `scripts/seed_legal.py`.
- **Endpoints**: `GET /api/v1/legal/{kind}` public (bản active);
  `POST /api/v1/legal/accept` (user đã đăng nhập, ghi acceptance các bản active);
  `/api/v1/me` trả thêm `needs_legal_acceptance` (bản active mới hơn bản đã chấp nhận);
  superadmin: GET list + POST publish version mới.
- **FE**: trang public `/terms`, `/privacy` (SPA route ngoài auth); modal chặn
  sau login khi `needs_legal_acceptance` (đọc + đồng ý mới dùng tiếp);
  superadmin trang Legal (textarea markdown + publish). Boss do superadmin tạo
  → không có signup checkbox; acceptance bắt ở lần đăng nhập.

## 2. Consent nhóm mô hình B (thêm vào notice hiện có)

- **Opt-out cá nhân**: bảng `capture_optouts(provider, provider_user_id UNIQUE
  theo cặp, display_name, created_at)`. Thành viên nhắn "@bot đừng ghi tin của
  tôi" → responder in_group gọi TOOL `opt_out_capture` (LLM quyết, KHÔNG
  keyword — đúng quy ước no-heuristic) → insert + bot xác nhận trong nhóm.
  `InboundIngest` bỏ qua (không persist) tin của người đã opt-out, mọi nhóm
  mọi boss trên provider đó. Chỉ chặn từ lúc opt-out (forward-only); xoá dữ
  liệu cũ = yêu cầu riêng qua superadmin (non-goal như spec erasure).
- **Đường ống sender**: `message.captured` + `ToolContext` mang thêm
  `sender_provider_id`/`sender_name` (additive) để tool biết ai yêu cầu.
- **Boss cam kết**: cột `users.group_consent_confirmed_at`. Lần đầu mở QR
  login Zalo phải gửi `consent_confirmed: true` (FE checkbox "Tôi có quyền
  thêm bot vào các nhóm của mình và sẽ thông báo cho thành viên") — thiếu thì
  409 code `consent_required`. Xác nhận 1 lần cho mọi kênh.

## 3. Definition of done

- Tests: acceptance flow (me flag → accept → hết flag; publish version mới →
  flag bật lại); opt-out (tool insert + ingest bỏ qua sender, boss/nhóm khác
  không ảnh hưởng); qr-login đòi cam kết lần đầu.
- Prompt in_group v9 (hướng dẫn opt_out_capture) — verify hành vi qua harness
  zalo khi tune vòng sau (LLM-dependent, không gate đợt này).
- pytest full + FE build sạch; gold/multipass/workload không regress.
