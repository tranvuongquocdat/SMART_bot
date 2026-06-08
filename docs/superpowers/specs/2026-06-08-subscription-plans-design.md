# Subscription Plans & Approval Flow — Design

**Date:** 2026-06-08  
**Status:** Approved

---

## Tổng quan

Hệ thống quản lý gói cước cho phép boss đăng ký nâng gói, upload minh chứng chuyển khoản, và superadmin duyệt thủ công qua web UI. Gói được lưu trong DB, superadmin có thể chỉnh thông số từng gói qua UI mà không cần deploy lại code. Thiết kế sẵn để tích hợp payment gateway tự động sau này.

### Tools vs Integrations

Hai khái niệm tách biệt hoàn toàn về cơ chế và ownership:

| | Tools | Integrations |
|---|---|---|
| Cơ chế | Built-in Python function, in-process | MCP server ngoài, kết nối qua URL |
| Ai add mới | Chỉ superadmin/platform (cần deploy) | Boss tự add bất kỳ MCP server URL |
| Boss quản lý | Toggle on/off từ catalog có sẵn | Self-service: add URL + auth token |
| Limit | `max_active_tools` | `mcp_slots` |
| Trang | `/app/admin/tools` | `/app/admin/integrations` |

Tools = platform-curated (như App Store). Integrations = self-service URL (như browser extension).

---

## Business model

- **Trial**: tự động, không cần duyệt, hết hạn → scheduler block
- **Starter / Pro**: boss chọn, upload chuyển khoản, superadmin duyệt → activate
- **Custom**: superadmin configure tay từng boss (giới hạn tùy chỉnh)
- **API**: boss dùng API hệ thống (bị cost cap) hoặc BYOK (không bị cap) — đều được
- **Notification superadmin**: chỉ qua web UI (badge pending trên nav)
- **Payment gateway**: chưa có, tích hợp sau mà không cần đổi schema

---

## Data model

### Bảng `plans` (mới)

```sql
id           SERIAL PRIMARY KEY
name         TEXT NOT NULL UNIQUE        -- slug: trial, starter, pro, custom
label        TEXT NOT NULL               -- tên hiển thị: "Starter", "Pro"...
limits_json  JSONB NOT NULL              -- xem cấu trúc bên dưới
is_active    BOOLEAN NOT NULL DEFAULT TRUE
sort_order   INTEGER NOT NULL DEFAULT 0
created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

**Cấu trúc `limits_json`:**
```json
{
  "max_groups": 5,
  "custom_channels": false,
  "mcp_slots": 0,
  "tools_tier": "standard",
  "duration_days": 30,
  "cost_cap_usd_daily": 2.0
}
```

| Field | Ý nghĩa |
|---|---|
| `max_active_groups` | Số nhóm active tối đa boss được chọn. `null` = unlimited |
| `max_active_tools` | Số built-in tools active tối đa. `null` = unlimited |
| `max_active_channels` | Số kênh active tối đa (bot accounts). `null` = unlimited |
| `mcp_slots` | Số MCP integration tối đa. `0` = không được dùng, `null` = unlimited |
| `duration_days` | Số ngày subscription khi approve. `null` = không hết hạn |
| `cost_cap_usd_daily` | Giới hạn chi phí LLM/ngày khi dùng API hệ thống. `null` = không giới hạn |

**Seed data 4 gói mặc định:**

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
status              TEXT NOT NULL DEFAULT 'pending'   -- pending/approved/rejected
note                TEXT                              -- ghi chú của boss
payment_proof_path  TEXT                              -- đường dẫn file upload
amount_paid_vnd     INTEGER                           -- số tiền boss khai
transfer_content    TEXT                              -- nội dung chuyển khoản
reviewer_note       TEXT                              -- lý do từ chối (nếu có)
reviewed_at         TIMESTAMPTZ
created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Constraint: boss chỉ có 1 request `pending` tại một thời điểm — enforce bằng partial unique index:
```sql
CREATE UNIQUE INDEX uq_one_pending_per_boss
  ON subscription_requests(boss_id)
  WHERE status = 'pending';
```

**Mở rộng cho payment gateway sau:** thêm `payment_ref TEXT`, bảng `payments` riêng link vào đây — không cần đổi schema hiện tại.

---

### Thay đổi bảng `users`

Thêm cột:
```sql
plan_id  INTEGER REFERENCES plans(id)   -- gói đang active
```

Các cột hiện có (`subscription_status`, `subscription_expiry`, `cost_cap_usd_daily`) giữ nguyên — khi approve, system copy giá trị từ `limits_json` vào đây để enforcement không cần join.

---

### Bảng `mcp_servers` (mới — thiết kế sẵn, implement sau)

```sql
id               BIGSERIAL PRIMARY KEY
boss_id          BIGINT NOT NULL REFERENCES users(id)
name             TEXT NOT NULL
url              TEXT NOT NULL
auth_token_enc   TEXT                    -- Fernet encrypted
enabled          BOOLEAN NOT NULL DEFAULT TRUE
created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

---

## Enforcement

Enforcement đọc thẳng từ `users` (không join `plans`) vì approve đã copy giá trị vào rồi.

| Limit | Điểm enforce | Hành động khi vượt |
|---|---|---|
| `max_active_groups` | UI khi boss toggle group active | Block toggle, show upgrade prompt |
| `max_active_tools` | UI khi boss toggle tool active | Block toggle, show upgrade prompt |
| `max_active_channels` | UI khi boss enable channel | Block action, show upgrade prompt |
| `mcp_slots` | UI khi boss add/enable MCP server | Block, show upgrade prompt |
| `cost_cap_usd_daily` | LLM gateway (`src/security/cost_cap.py`) | Agent trả lỗi, không gọi LLM |
| `subscription_status = expired/canceled` | Đầu mỗi agent call | Block toàn bộ, trả thông báo hết hạn |

Enforcement chủ yếu ở **frontend** (block UI action + show upgrade modal) và **API** (trả 400 nếu vượt limit). Agent chỉ load tools/groups đang active — không cần check limit tại runtime.

### Boss quản lý active items

- **Groups**: `/app/admin/groups` — mỗi group có toggle Active/Inactive. Badge "3/5 nhóm active".
- **Tools**: `/app/admin/tools` — grid tất cả built-in tools platform cung cấp, toggle từng cái. Badge "6/10 tools active".
- **Channels**: `/app/admin/channels` — enable/disable bot account. Badge "1/3 kênh active".
- **Integrations**: `/app/admin/integrations` — tự add MCP server URL + auth. Badge "1/2 integrations".

---

## Luồng request & approve

### Boss gửi request

1. Vào `/app/admin/subscription`
2. Xem cards các gói (gói đang active disabled)
3. Click "Đăng ký" → modal hiện ra:
   - Ghi chú / lý do (optional)
   - Số tiền chuyển khoản (VND)
   - Nội dung chuyển khoản
   - Upload ảnh minh chứng (jpg/png/pdf, max 5MB)
4. Submit → `subscription_requests` row tạo với `status=pending`
5. Boss thấy banner "Đang chờ duyệt" — không thể gửi thêm request mới khi còn pending

### Superadmin duyệt

1. Nav item "Subscriptions" hiện badge số pending
2. Trang `/app/superadmin/subscriptions`:
   - Table: boss email | gói yêu cầu | ngày gửi | status
   - Filter tabs: Pending / Approved / Rejected
3. Click row → detail panel:
   - Info boss (email, gói hiện tại, ngày tạo)
   - Gói yêu cầu + preview limits
   - Ghi chú của boss
   - Ảnh minh chứng (click xem full)
   - Số tiền + nội dung CK
   - Override limits (optional): chỉnh max_groups, mcp_slots... trước khi duyệt
   - Actions: [Từ chối] | [Duyệt]
4. **Approve** → system:
   - `users.plan_id = plan_id`
   - `users.subscription_status = 'active'`
   - `users.subscription_expiry = NOW() + interval 'X days'` (từ limits_json hoặc override)
   - `users.cost_cap_usd_daily = limits_json.cost_cap_usd_daily` (hoặc override)
   - `subscription_requests.status = 'approved'`, `reviewed_at = NOW()`
5. **Reject** → nhập lý do → `status = 'rejected'`, `reviewer_note = lý do`

### State machine request

```
pending → approved   (superadmin duyệt)
pending → rejected   (superadmin từ chối)
```

Boss có thể tạo request mới sau khi rejected hoặc sau khi đã approved (để nâng gói tiếp).

---

## UI

### Admin — `/app/admin/subscription` (mở rộng trang hiện có)

**Section 1 — Gói hiện tại** (đã có, giữ nguyên):
- Badge status, tên gói, ngày hết hạn, cost cap, số nhóm đang dùng/tổng

**Section 2 — Nâng cấp gói** (mới):
- Grid card 4 gói
- Mỗi card: tên, giá (nếu có), highlights (số nhóm, MCP, tool tier)
- Gói đang active: disabled + badge "Đang dùng"
- Gói thấp hơn gói hiện tại: disabled
- Gói cao hơn: button "Đăng ký"
- Khi còn pending: tất cả disabled, banner "Đang chờ duyệt gói X"

**Section 3 — Lịch sử yêu cầu** (mới):
- List: tên gói | ngày gửi | status badge | reviewer note (nếu rejected)

### Superadmin — `/app/superadmin/subscriptions` (trang mới)

- Table với filter Pending / All
- Badge đỏ trên nav khi có pending
- Detail panel: thông tin boss, gói, minh chứng, override fields, approve/reject

### Superadmin — `/app/superadmin/plans` (trang mới)

- Table list gói: name, label, limits summary, is_active
- Form tạo/sửa gói: điền các field trong limits_json qua UI
- Không thể xóa gói đang có user dùng

---

## File upload

- Endpoint: `POST /api/v1/admin/subscription/requests` (multipart form)
- Lưu tại: `uploads/payment_proofs/<uuid>.<ext>`
- Serve tại: `GET /api/v1/superadmin/payment-proof/<filename>` (chỉ superadmin)
- Giới hạn: 5MB, chấp nhận jpg/png/pdf

---

## API endpoints

### Admin (boss)
```
GET  /api/v1/admin/subscription          — thông tin gói hiện tại (đã có)
GET  /api/v1/admin/subscription/plans    — danh sách gói active
GET  /api/v1/admin/subscription/requests — lịch sử request của boss
POST /api/v1/admin/subscription/requests — tạo request mới (multipart)
```

### Superadmin
```
GET   /api/v1/superadmin/subscription-requests              — list (filter by status)
GET   /api/v1/superadmin/subscription-requests/:id          — detail
POST  /api/v1/superadmin/subscription-requests/:id/approve  — duyệt (body: overrides)
POST  /api/v1/superadmin/subscription-requests/:id/reject   — từ chối (body: note)
GET   /api/v1/superadmin/payment-proof/:filename            — xem ảnh CK

GET   /api/v1/superadmin/plans           — list gói
POST  /api/v1/superadmin/plans           — tạo gói
PATCH /api/v1/superadmin/plans/:id       — sửa gói
```

---

## Extensibility notes

- **Payment gateway**: thêm `payment_ref TEXT` vào `subscription_requests` + bảng `payments` riêng. Auto-approve on webhook thay manual approve. Không đổi schema hiện tại.
- **MCP integration**: bảng `mcp_servers` đã thiết kế sẵn. Khi implement, agent loader đọc danh sách server của boss, check `mcp_slots`, gọi tools qua MCP protocol chuẩn.
- **Thêm limit mới vào gói**: chỉ cần thêm field vào `limits_json` + thêm enforcement point — không cần migration schema `plans`.
