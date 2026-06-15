# Subscription Plans & Approval Flow — Design

**Date:** 2026-06-08  
**Status:** Approved

---

## Tổng quan

Hệ thống quản lý gói cước cho phép boss đăng ký nâng gói, upload minh chứng chuyển khoản, và superadmin duyệt thủ công qua web UI. Gói lưu trong DB, superadmin chỉnh thông số qua UI không cần deploy lại. Thiết kế sẵn để tích hợp payment gateway tự động sau này.

### Tools vs Integrations

| | Tools | Integrations |
|---|---|---|
| Cơ chế | Built-in Python, in-process | MCP server ngoài, kết nối qua URL |
| Ai add mới | Chỉ superadmin/platform (cần deploy) | Superadmin add vào catalog HOẶC boss tự add URL riêng |
| Boss quản lý | Toggle on/off từ catalog platform | Pick từ catalog có sẵn hoặc add custom URL + auth |
| Limit | `max_active_tools` | `mcp_slots` (catalog + custom đều tính chung) |
| Trang | `/app/admin/tools` | `/app/admin/integrations` |

Tools = platform-curated. Integrations = superadmin catalog + boss self-service URL.

---

## Business model

- **Trial**: tự động, không cần duyệt, hết hạn → degrade
- **Starter / Pro**: boss chọn, upload chuyển khoản, superadmin duyệt → activate
- **Custom**: superadmin configure tay từng boss (override limit per-boss)
- **API**: boss dùng API hệ thống (bị cost cap) hoặc BYOK (không bị cap)
- **Notification superadmin**: chỉ qua web UI (badge pending trên nav)
- **Payment gateway**: chưa có, tích hợp sau không cần đổi schema

---

## Data model

### Bảng `plans` (mới)

```sql
id           SERIAL PRIMARY KEY
name         TEXT NOT NULL UNIQUE
label        TEXT NOT NULL
limits_json  JSONB NOT NULL
is_active    BOOLEAN NOT NULL DEFAULT TRUE
sort_order   INTEGER NOT NULL DEFAULT 0
created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

**Cấu trúc `limits_json`:**
```json
{
  "max_active_groups": 5,
  "max_active_tools": 10,
  "max_active_channels": 1,
  "mcp_slots": 0,
  "duration_days": 30,
  "cost_cap_usd_daily": 2.0
}
```

| Field | Ý nghĩa |
|---|---|
| `max_active_groups` | Số nhóm active tối đa boss được chọn. `null` = unlimited |
| `max_active_tools` | Số built-in tools active tối đa. `null` = unlimited |
| `max_active_channels` | Số kênh (bot account) active tối đa. `null` = unlimited |
| `mcp_slots` | Số MCP integration enabled tối đa (catalog + custom). `null` = unlimited |
| `duration_days` | Số ngày subscription khi approve. `null` = không hết hạn |
| `cost_cap_usd_daily` | Giới hạn LLM cost/ngày khi dùng API hệ thống. `null` = không giới hạn |

**Seed data:**

| name | max_active_groups | max_active_tools | max_active_channels | mcp_slots | duration_days | cost_cap |
|---|---|---|---|---|---|---|
| trial | 2 | 5 | 1 | 0 | 14 | 0.5 |
| starter | 5 | 10 | 1 | 0 | 30 | 2.0 |
| pro | 30 | null | 3 | 2 | 30 | 5.0 |
| custom | null | null | null | null | null | null |

---

### Bảng `subscription_requests` (mới)

```sql
id                  BIGSERIAL PRIMARY KEY
boss_id             BIGINT NOT NULL REFERENCES users(id)
plan_id             INTEGER NOT NULL REFERENCES plans(id)
status              TEXT NOT NULL DEFAULT 'pending'
  -- pending / approved / rejected / cancelled
note                TEXT             -- ghi chú của boss khi đăng ký
payment_proof_path  TEXT             -- ảnh minh chứng chuyển khoản
amount_paid_vnd     INTEGER          -- số tiền boss khai
transfer_content    TEXT             -- nội dung chuyển khoản
reviewer_note       TEXT             -- lý do từ chối (nếu rejected)
reviewed_at         TIMESTAMPTZ
cancel_reason       TEXT             -- lý do boss huỷ
refund_requested    BOOLEAN NOT NULL DEFAULT FALSE
refund_qr_path      TEXT             -- ảnh QR bank / số TK để superadmin refund
cancelled_at        TIMESTAMPTZ
created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Partial unique index — chỉ 1 request pending tại một thời điểm:
```sql
CREATE UNIQUE INDEX uq_one_pending_per_boss
  ON subscription_requests(boss_id)
  WHERE status = 'pending';
```

**Mở rộng payment gateway sau:** thêm `payment_ref TEXT` + bảng `payments` riêng, không đổi schema này.

---

### Bảng `mcp_catalog` (mới — platform-level)

```sql
id                    SERIAL PRIMARY KEY
name                  TEXT NOT NULL
description           TEXT
url                   TEXT NOT NULL
config_template_json  JSONB   -- các field auth cần điền: [{key, label, secret}]
icon_url              TEXT
is_active             BOOLEAN NOT NULL DEFAULT TRUE
created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Superadmin add vào đây (Google Calendar, Notion...). Boss pick từ catalog → tạo `mcp_servers` row với `catalog_id` set.

---

### Bảng `mcp_servers` (mới — per-boss)

```sql
id              BIGSERIAL PRIMARY KEY
boss_id         BIGINT NOT NULL REFERENCES users(id)
catalog_id      INTEGER REFERENCES mcp_catalog(id)  -- null nếu custom URL
name            TEXT NOT NULL
url             TEXT NOT NULL
auth_json_enc   TEXT             -- Fernet encrypted
enabled         BOOLEAN NOT NULL DEFAULT TRUE
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Catalog pick và custom URL đều tạo row ở đây. Cả 2 loại đều tính vào `mcp_slots`.

---

### Thay đổi bảng `users`

```sql
plan_id              INTEGER REFERENCES plans(id)
plan_overrides_json  JSONB DEFAULT '{}'   -- override limit per-boss: {"max_active_groups": 50}
```

Các cột hiện có (`subscription_status`, `subscription_expiry`, `cost_cap_usd_daily`) giữ nguyên.

**Effective limit** = `plan.limits_json[key]` được override bởi `users.plan_overrides_json[key]` nếu có key đó. Superadmin dùng override khi duyệt gói Custom hoặc muốn cấp exception cho 1 boss.

---

## Enforcement

### Hai chiều của limit

**Chiều 1 — Bật thêm vượt limit → block ngay:**
Boss toggle active item thứ N+1 → frontend block, show modal upgrade.

**Chiều 2 — Đang over-limit do plan thay đổi → bắt resolve:**
Khi plan thay đổi (approve gói thấp hơn, expire, superadmin override) → system tính `over_limit_items`. Nếu có → boss phải resolve trước khi dùng tiếp (tắt bớt đủ item hoặc upgrade).

### Resolution flow (khi over-limit)

Hiển thị **resolution screen** block toàn bộ dashboard:
```
"Gói của bạn đã thay đổi. Bạn đang có [X nhóm / Y tools / Z kênh] vượt giới hạn mới.
Vui lòng tắt bớt hoặc nâng cấp gói để tiếp tục."

[Danh sách nhóm đang active] → boss tick tắt những cái không cần
[Danh sách tools đang active] → tương tự
[Danh sách kênh đang active] → tương tự
[Nút: Đăng ký nâng cấp gói]
```

Bot vẫn không respond trong các groups đang active cho đến khi resolved.

### Bảng enforcement

| Limit | Khi activate (chiều 1) | Khi over-limit (chiều 2) |
|---|---|---|
| `max_active_groups` | Block toggle, show upgrade modal | Resolution screen |
| `max_active_tools` | Block toggle, show upgrade modal | Resolution screen |
| `max_active_channels` | Block enable, show upgrade modal | Resolution screen |
| `mcp_slots` | Block enable, show upgrade modal | Resolution screen |
| `cost_cap_usd_daily` | — | LLM gateway block, agent trả lỗi |
| `expired / cancelled` | — | Block toàn bộ, redirect subscription page |

### expired_grace (30 ngày sau hết hạn)

- Degrade về Trial limits (`max_active_groups=2`, `max_active_tools=5`, `max_active_channels=1`, `mcp_slots=0`)
- Trigger resolution flow nếu currently over Trial limits
- Warning banner trên dashboard: "Gói đã hết hạn, đang dùng giới hạn Trial. Gia hạn để khôi phục."
- Sau 30 ngày → `expired` → block hoàn toàn

### Agent runtime

Agent chỉ load tools và groups đang `enabled/active` của boss — không check limit tại runtime. Enforcement xảy ra hoàn toàn ở tầng UI + API.

---

## Luồng request & approve

### Boss gửi request nâng gói

1. Vào `/app/admin/subscription` → xem plan cards
2. Click "Đăng ký" trên gói muốn nâng → modal:
   - Ghi chú / lý do (optional)
   - Số tiền chuyển khoản (VND)
   - Nội dung chuyển khoản
   - Upload ảnh minh chứng (jpg/png/pdf, max 5MB)
3. Submit → `status = pending`
4. Banner "Đang chờ duyệt gói X" — không thể gửi thêm request

### Boss huỷ request

1. Boss click "Huỷ yêu cầu" trên banner pending
2. Modal: "Bạn có cần hoàn tiền không?"
   - Không → confirm huỷ
   - Có → hiện field upload ảnh QR/số tài khoản ngân hàng + ghi chú
3. `status = cancelled`, `refund_requested`, `refund_qr_path` lưu vào DB
4. Superadmin thấy cancelled request có flag refund trong list → xử lý thủ công

### Superadmin duyệt

1. Nav badge hiện số pending
2. `/app/superadmin/subscriptions` — table: boss | gói | ngày | status
3. Click row → detail:
   - Info boss (email, gói hiện tại, ngày tạo)
   - Gói yêu cầu + preview limits
   - Ghi chú boss, ảnh minh chứng, số tiền + nội dung CK
   - Override (optional): chỉnh từng limit trước khi duyệt
   - [Từ chối] | [Duyệt]
4. **Approve** → atomic transaction:
   - `users.plan_id = plan_id`
   - `users.plan_overrides_json = overrides` (nếu có)
   - `users.subscription_status = 'active'`
   - `users.subscription_expiry = NOW() + duration_days`
   - `users.cost_cap_usd_daily = effective cost cap`
   - Check over-limit → nếu có, boss sẽ thấy resolution screen lần đăng nhập tiếp
   - `request.status = 'approved'`
5. **Reject** → nhập lý do → `status = rejected`

### State machine request

```
pending ──→ approved   (superadmin duyệt)
pending ──→ rejected   (superadmin từ chối)
pending ──→ cancelled  (boss huỷ)
  └─ refund_requested = true  →  superadmin refund thủ công
```

Boss tạo request mới được sau khi rejected hoặc cancelled (không phải pending).  
Sau approved, boss tạo request mới để nâng tiếp hoặc đổi gói.

---

## Edge cases

| Tình huống | Xử lý |
|---|---|
| Plan expire → boss đang có 30 active groups, limit mới = 2 | expired_grace degrade về Trial limits → trigger resolution screen |
| Superadmin đổi plan boss trực tiếp | Tính over-limit ngay → boss thấy resolution screen lần login tiếp |
| Boss submit 2 request cùng lúc (2 tab) | Partial unique index reject insert thứ 2 → API trả 409 |
| Approve gói thấp hơn gói hiện tại (downgrade) | Cho phép, trigger over-limit check sau approve |
| Boss huỷ request đã approved | Không cho huỷ approved — chỉ pending mới huỷ được |
| Superadmin sửa `limits_json` của plan đang có user dùng | Không tự apply cho user hiện tại — chỉ áp dụng cho approve mới. User hiện tại giữ nguyên cho đến khi gia hạn. |
| Boss ở gói Custom (null limits), superadmin override một số field | Chỉ các field có trong `plan_overrides_json` mới bị ghi đè — field không có thì vẫn null (unlimited) |
| `refund_requested = true` nhưng boss chưa upload QR | Cho phép — superadmin thấy flag, liên hệ boss ngoài hệ thống |

---

## UI

### Admin — `/app/admin/subscription`

**Section 1 — Gói hiện tại** (đã có, mở rộng):
- Tên gói, status badge, ngày hết hạn, cost cap
- Usage bars: `X/N nhóm active`, `X/N tools`, `X/N kênh`, `X/N integrations`
- Warning banner nếu `expired_grace`

**Section 2 — Nâng cấp gói:**
- Grid card 4 gói, mỗi card: tên, giá, highlights
- Gói đang active: badge "Đang dùng", disabled
- Gói thấp hơn: disabled (không downgrade qua UI)
- Khi pending: tất cả disabled, banner + nút "Huỷ yêu cầu"

**Section 3 — Lịch sử yêu cầu:**
- List: tên gói | ngày gửi | status badge | reviewer note nếu rejected

**Resolution screen** (overlay khi over-limit):
- Danh sách items vượt limit, boss tick tắt để resolve
- Nút "Đăng ký nâng cấp"

### Superadmin — `/app/superadmin/subscriptions` (trang mới)

- Table filter: Pending / Cancelled (refund) / All
- Badge đỏ: pending count; badge vàng: refund pending count
- Detail panel: info boss, gói, minh chứng, ảnh QR refund (nếu có), override fields, approve/reject

### Superadmin — `/app/superadmin/plans` (trang mới)

- List gói, form tạo/sửa limits_json qua UI
- Không xóa được gói đang có user dùng

### Superadmin — `/app/superadmin/integrations` (trang mới — MCP catalog)

- List MCP catalog entries
- Add entry: name, URL, config_template_json, icon

---

## File upload

- Payment proof: `POST /api/v1/admin/subscription/requests` (multipart)
- Refund QR: `POST /api/v1/admin/subscription/requests/:id/cancel` (multipart)
- Lưu tại: `uploads/payment_proofs/<uuid>.<ext>`
- Serve: `GET /api/v1/superadmin/payment-proof/<filename>` (chỉ superadmin)
- Giới hạn: 5MB, jpg/png/pdf

---

## API endpoints

### Admin (boss)
```
GET    /api/v1/admin/subscription                      — info gói hiện tại
GET    /api/v1/admin/subscription/plans                — danh sách gói
GET    /api/v1/admin/subscription/requests             — lịch sử request
POST   /api/v1/admin/subscription/requests             — tạo request (multipart)
POST   /api/v1/admin/subscription/requests/:id/cancel  — huỷ pending (multipart, refund QR optional)

GET    /api/v1/admin/tools                             — danh sách tools + active status
PATCH  /api/v1/admin/tools/:name/toggle                — bật/tắt tool

GET    /api/v1/admin/integrations                      — danh sách MCP servers + catalog
POST   /api/v1/admin/integrations                      — add MCP server (catalog pick hoặc custom)
PATCH  /api/v1/admin/integrations/:id/toggle           — enable/disable
DELETE /api/v1/admin/integrations/:id                  — xoá

GET    /api/v1/admin/subscription/limits               — effective limits của boss hiện tại
```

### Superadmin
```
GET    /api/v1/superadmin/subscription-requests              — list (filter: status)
GET    /api/v1/superadmin/subscription-requests/:id          — detail
POST   /api/v1/superadmin/subscription-requests/:id/approve  — duyệt (body: overrides)
POST   /api/v1/superadmin/subscription-requests/:id/reject   — từ chối (body: note)
GET    /api/v1/superadmin/payment-proof/:filename            — xem file

GET    /api/v1/superadmin/plans                              — list gói
POST   /api/v1/superadmin/plans                              — tạo gói
PATCH  /api/v1/superadmin/plans/:id                          — sửa gói

GET    /api/v1/superadmin/mcp-catalog                        — list catalog entries
POST   /api/v1/superadmin/mcp-catalog                        — add entry
PATCH  /api/v1/superadmin/mcp-catalog/:id                    — sửa entry
```

---

## Extensibility notes

- **Payment gateway**: thêm `payment_ref TEXT` vào `subscription_requests` + bảng `payments` riêng. Auto-approve on webhook. Schema không đổi.
- **Thêm limit dimension mới**: thêm field vào `limits_json` + 1 enforcement point — không cần migration `plans`.
- **Per-boss fine-grained override**: `plan_overrides_json` trên `users` đã sẵn sàng.
