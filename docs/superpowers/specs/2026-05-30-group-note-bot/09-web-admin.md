[← Index](./README.md)

# §9. Web admin

## 9.0 Design principles

UI hướng "công cụ chuyên nghiệp", không "AI demo":

- **Typography**: Inter / system sans cho UI; mono cho data (msg id,
  cost, token). Không decorative font.
- **Color**: nền trắng / xám rất nhạt. Accent 1 màu chính (xanh đậm
  hoặc tím đậm). Status dùng badge text ("Đang chạy", "Trễ", "Tạm
  dừng") + chấm tròn màu, **không emoji**.
- **Spacing**: dense hơn web SaaS dân dụng — hướng tới Linear /
  Stripe Dashboard layout. Sếp xem nhiều data trong 1 lần.
- **No emoji** trong UI text, button label, system prompt mặc định.
  Tham khảo: Linear, Notion, Stripe.
- **No "✨ AI / ⚡ Powered" stickers.** Bot xưng "em", không tự gọi
  "AI assistant" trong copy hướng người dùng.
- **Empty state** = text giải thích + 1 CTA, không illustration vẽ.
- **Loading** = skeleton hoặc subtle spinner; không "thinking..." text.

## 9.1 Auth & session

- **Google OAuth** (primary) qua Authlib. Email/password (fallback) cho
  ai không có Google account.
- Session cookie HTTP-only, Secure, SameSite=Lax, TTL 30 ngày.
- `role` từ `users.role`. Superadmin auto-set khi email trong env
  `SUPERADMIN_EMAILS`.

## 9.2 Sitemap (user pages)

```
/login                   — Google OAuth + email/password
/                        — Dashboard
/groups                  — List group đã capture
/groups/:id              — Group detail (note + history + action items + members)
/action-items            — Tổng hợp action item cross-group
/projects                — Projects view: action item + reminder cross-group, theo deadline
/reminders               — List/edit/cancel reminder đã set
/digests                 — (Phase 1, MVP show "Sắp có")
/channels                — Connect Zalo (MVP single-channel). Hiện mode hiện tại + nút switch platform↔self ([§3.10](./03-identity-channel-linking.md#310-switch-mode)).
/plugins                 — Marketplace + manage installed
/plugins/:id             — Plugin detail (OAuth + settings form)
/usage                   — Token + cost dashboard
/settings/general        — Tên bot, ngôn ngữ, TZ, retention
/settings/ai             — Provider + 3 slot model (smart/fast/vision) + custom provider
/settings/account        — Email, đổi mật khẩu, đăng xuất
/subscription            — Gói + VietQR + lịch sử thanh toán
```

## 9.3 Sitemap (superadmin pages)

Chỉ visible khi `role=superadmin`:

```
/admin/bosses            — List + detail + set expiry + add payment + assign bot acc
/admin/bot-accounts      — Filter: Platform | Boss-owned. Pool Zalo: list, login/relogin, assign, traffic.
/admin/bot-accounts/:id  — Detail platform: status, login flow, msgs in/out, assignment list, cap edit.
                           Detail boss-owned: read-only (status, owner, traffic) + [Disable] với audit log.
/admin/models            — Model registry CRUD (provider, model, tier, ctx, cost, is_default)
/admin/feature-routing   — Bảng feature → tier (edit live)
/admin/prompts           — Prompts registry: list key, active version, version history, editor, [Set active] [Rollback] ([§7.6](./07-llm-abstraction.md#76-prompt-registry))
/admin/templates         — Note templates: list system + custom, edit sections_json ([§4.9](./04-group-note.md#49-note-template-system)). MVP read-only system; Phase 1 add custom editor.
/admin/audit-log         — Mutations log (disable boss-owned acc, prompt edit, model CRUD)
/admin/payments          — Log payment + [+ Add payment]
/admin/revenue           — Chart MRR / ARR / top customer
```

### `/admin/bot-accounts` chi tiết

```
┌─────────────────────────────────────────────────────────────────────┐
│ Bot accounts          [Platform] [Boss-owned]      [+ Thêm acc]     │
├─────────────────────────────────────────────────────────────────────┤
│ (Tab Platform — anh quản đầy đủ)                                    │
│ Số/handle    │ Status        │ Sếp serve │ Cap │ 7d msg in │ Action │
│ 0903xxx789   │ ● Active      │ 3         │ 5   │ 1,247     │ Detail │
│ 0905xxx101   │ ● Rate-limit  │ 2         │ 5   │ 982       │ Detail │
│ 0908xxx234   │ ● Logged-out  │ 0         │ 5   │ 0         │ Detail │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ (Tab Boss-owned — read-only, không đọc credentials)                 │
│ Số/handle    │ Owner sếp     │ Status       │ 7d msg in │ Action    │
│ 0907xxx555   │ Anh Đạt (#42) │ ● Active     │ 410       │ [Disable] │
│ 0902xxx123   │ Chị Mai (#51) │ ● Logged-out │ 0         │ [Disable] │
└─────────────────────────────────────────────────────────────────────┘

Click row Platform → Detail:
  - QR/cookie login flow (Zalo personal)
  - Force re-login button
  - Pause / Resume
  - Cap edit (max_assigned_bosses)
  - List sếp đang được gán + accept status + [Reassign] per row
  - Counter: msg in/out tổng, msg 7d, latency reply trung bình
  - Log lỗi gần nhất

Click row Boss-owned → Detail (read-only):
  - Status, owner, traffic counter
  - Log lỗi gần nhất (cho debug, không expose credentials)
  - [Disable] với required reason text → audit_log
  - Anh KHÔNG re-login, KHÔNG đọc credentials, KHÔNG assign sếp khác
```

### `/admin/models` chi tiết

```
┌─────────────────────────────────────────────────────────────────┐
│ Models                                       [+ Thêm model]     │
├─────────────────────────────────────────────────────────────────┤
│ Name                  │ Provider │ Tier  │ Default│ Active │ ...│
│ gpt-4o-mini           │ openai   │ smart │ ✓      │ ✓      │    │
│ llama-3.3-70b         │ groq     │ fast  │ ✓      │ ✓      │    │
│ claude-haiku-4-5      │ anthropic│ smart │        │ ✓      │    │
└─────────────────────────────────────────────────────────────────┘

Edit row: name, provider, endpoint_kind, base_url, tier, ctx_max,
capabilities (multi-select), cost in/out, is_platform_default, is_active.
Sếp nào chưa config sẽ tự dùng model có is_platform_default=true cùng tier.
```

## 9.4 Dashboard widgets

```
┌────────────┬────────────┬────────────┬────────────┐
│ Groups     │ Open       │ Reminder   │ Tháng này  │
│ N / M kênh │ K việc     │ P sắp đến  │ $X /       │
│            │            │            │ Y M token  │
└────────────┴────────────┴────────────┴────────────┘
┌──────────────────────────┬──────────────────────────┐
│ Hoạt động 7 ngày qua     │ Cảnh báo                 │
│ [bar chart messages/day] │ • Bot acc Zalo cần       │
│                          │   relogin                │
│                          │ • 3 task quá hạn         │
│                          │ • Reminder gần nhất:     │
│                          │   T5 15:00               │
└──────────────────────────┴──────────────────────────┘
```

## 9.5 Group detail page

Mục đích = sếp thấy bot đang làm gì trong group, edit note, scan action item:

```
┌───────────────────────────────────────────────────┐
│ ← Groups · Team Sale Q2                          │
│                                                   │
│ [Note] [History] [Action Items] [Members]        │
│ ───────                                           │
│                                                   │
│ ┌─ Group note ─────────────────────────────────┐ │
│ │ # Team Sale Q2                                │ │
│ │ Cập nhật 30/5 14:32 · 47 msg/ngày             │ │
│ │ ...                                           │ │
│ │ (markdown rendered, click Edit để sửa)        │ │
│ └──────────────────────────────────────────────┘ │
│                                                   │
│ [Edit] [Refresh now] [Export]                    │
└───────────────────────────────────────────────────┘
```

- **Note tab**: render note + Edit/Refresh/Export. **Live preview SSE**:
  khi NoteUpdater chạy (sau debounce/threshold), page subscribe
  `/api/groups/:id/events` (Server-Sent Events). Event `note.updated`
  từ EventBus ([§14.1](./14-performance-observability.md#141-eventbus-internal))
  trigger page re-render diff highlight section thay đổi → cảm giác
  "đang sống" như meeting note tool.
- **History tab**: timeline version note + diff view
- **Action Items tab**: filter view của section "Việc đang mở"
- **Pinned tab**: list từ `pins` table (§6) — sếp xem mọi tin đã pin
- **Members tab**: list người gửi (display name), count message 7d
- **Template tab**: chọn note template ([§4.9](./04-group-note.md#49-note-template-system))

## 9.6 Channel wizard — dual-mode

`/channels` step 1 — chọn mode:

```
┌──────────────────────────────────────────────────────────────┐
│ Kết nối Zalo                                                  │
│                                                                │
│ ○ Dùng acc bot do platform cấp                                │
│   Anh đợi admin gán 1 acc bot, accept rồi chat qua acc đó.    │
│   Phù hợp khi: anh muốn nhanh, không cần kiểm soát acc.       │
│                                                                │
│ ○ Tự kết nối acc Zalo của tôi                                 │
│   Anh đăng nhập acc Zalo cá nhân, acc đó trở thành bot riêng. │
│   Phù hợp khi: anh muốn data đi qua acc của mình, full control│
│                                                                │
│                                              [Tiếp]            │
└──────────────────────────────────────────────────────────────┘
```

### Flow A — Platform mode

```
/channels
  ┌─────────────────────────────────────────────┐
  │ Zalo (Platform)                             │
  │ Trạng thái: Đang chờ admin gán acc...       │
  └─────────────────────────────────────────────┘

  (Khi admin click Auto-assign)
  ▼
  ┌─────────────────────────────────────────────┐
  │ Zalo (Platform)                             │
  │ Admin gán acc 0903xxx789. Accept?           │
  │             [Accept]  [Decline]              │
  └─────────────────────────────────────────────┘

  ▼ (Click Accept)
  ┌─────────────────────────────────────────────┐
  │ Zalo (Platform — 0903xxx789)                │
  │ Anh nhắn /start <token> tới 0903xxx789      │
  │ trên Zalo. (token có hiệu lực 10 phút)      │
  │              [Copy số]  [Copy token]         │
  └─────────────────────────────────────────────┘

  ▼ (Sếp gửi /start <token> trên Zalo)
  ▼ Bot reply ack, web auto-refresh
  ┌─────────────────────────────────────────────┐
  │ Zalo (Platform — 0903xxx789)  ● Đã kết nối  │
  │ [Đổi sang Tự kết nối acc của tôi]            │
  └─────────────────────────────────────────────┘
```

### Flow B — Self-managed mode

```
/channels → chọn "Tự kết nối acc Zalo của tôi" → [Tiếp]
  ▼
  Wizard step 2 — chọn cách login:
  ○ Scan QR (mở Zalo trên điện thoại → tap "Quét QR")
  ○ Paste cookies (advanced — xuất từ browser extension)

  ▼ (Scan QR)
  Hiện QR code lớn + countdown 60s
  Sếp scan trên app → server detect login → success
  ▼
  ┌─────────────────────────────────────────────┐
  │ Zalo (Self-managed — 0907xxx555)            │
  │ ● Đã kết nối                                 │
  │ [Đổi sang Platform]                          │
  └─────────────────────────────────────────────┘
```

Khi mode = self và acc bị logged_out → page hiện nút "Login lại" cho sếp tự xử.

## 9.7 Settings AI — 3 slot model

Sếp pick model cho từng vai trò khác nhau. UI giải thích rõ vì sao
cần 3 slot:

```
┌─────────────────────────────────────────────────────────────────┐
│ Cấu hình AI                                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Em dùng 3 model khác nhau cho 3 mục đích, anh chọn cho từng     │
│ slot. Có thể chọn cùng 1 model cho cả 3 nếu muốn đơn giản.      │
│                                                                 │
│ ┌─ Smart  (suy luận, tóm tắt, trả lời câu hỏi dài) ──────────┐ │
│ │ Provider: [OpenAI       ▾]                                  │ │
│ │ Model:    [gpt-4o       ▾]                                  │ │
│ │ Dùng cho: tóm tắt group, Q&A có search lịch sử, viết note  │ │
│ │ Chi phí ước tính: $X / 1000 cuộc đối thoại                  │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ ┌─ Fast  (phản hồi nhanh, việc đơn giản) ─────────────────────┐ │
│ │ Provider: [Groq         ▾]                                  │ │
│ │ Model:    [llama-3.3-70b▾]                                  │ │
│ │ Dùng cho: xác nhận ngắn, phân loại tin, trích việc cần làm │ │
│ │ Chi phí ước tính: $X / 1000 cuộc đối thoại                  │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ ┌─ Vision  (đọc ảnh) ─────────────────────────────────────────┐ │
│ │ Provider: [OpenAI       ▾]                                  │ │
│ │ Model:    [gpt-4o-mini  ▾] (đề xuất: model nhẹ để tiết kiệm)│ │
│ │ Dùng cho: nhận diện nội dung ảnh trong group (bill,         │ │
│ │           screenshot, ảnh sản phẩm), đọc text trên ảnh      │ │
│ │ Chi phí ước tính: $X / 1000 ảnh                             │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ ┌─ API Keys (anh tự cung cấp — BYO) ──────────────────────────┐ │
│ │ OpenAI:     [••••••••••••] [Test]                           │ │
│ │ Groq:       [••••••••••••] [Test]                           │ │
│ │ Anthropic:  [thêm key]                                      │ │
│ │ Gemini:     [thêm key]                                      │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│                                            [Huỷ]  [Lưu]         │
└─────────────────────────────────────────────────────────────────┘
```

**Vì sao cần 3 slot:**
- **Smart đắt nhưng giỏi** — dùng cho việc cần suy luận, không nhiều
  call.
- **Fast rẻ và nhanh** — dùng cho việc lặp lại nhiều (trích task từ
  mỗi message) hoặc cần latency thấp (sếp tag bot trong group, đợi 5s
  là chậm).
- **Vision riêng** — model có vision thường đắt; tách slot để sếp
  chọn model VISION RẺ cho việc đọc ảnh tự động (~hàng trăm ảnh/ngày
  ở group đông), giữ smart đắt cho reasoning thật sự cần.

**Fallback:**
- Slot trống → dùng model mặc định platform.
- Smart model có vision capability → có thể đại diện vision slot khi
  vision slot trống (cảnh báo trên save nếu detect được).

Model dropdown chỉ list model `is_active=true` ở `/admin/models`.

## 9.8 Reminders & Projects

`/reminders` (user page):

```
┌─────────────────────────────────────────────────────┐
│ Reminders                              [+ Tạo mới]  │
├─────────────────────────────────────────────────────┤
│ Filter: [Sắp đến][Đã chạy][Đã huỷ]  Group: [Tất cả]│
├─────────────────────────────────────────────────────┤
│ T5 15:00  Nhắc anh Tân nộp báo cáo  · Sale Q2       │
│ T6 09:00  Họp với đối tác A          · Đối tác A    │
│ ...                                                  │
└─────────────────────────────────────────────────────┘
```

Row click → edit: text, due_at, scope (group/dm), target, recurring.
"Tạo mới" cũng có form đầy đủ — nhưng UX chính vẫn là set qua chat (em
xử lý parse natural language).

`/projects` (user page) = view, **không entity riêng**:

```
┌─────────────────────────────────────────────────────┐
│ Projects (cross-group)                              │
├─────────────────────────────────────────────────────┤
│ Group        │ Open │ Trễ │ Reminder │ Last update  │
│ Sale Q2      │ 8    │ 2   │ 3        │ 30/5 14:32   │
│ Đối tác A    │ 4    │ 0   │ 1        │ 30/5 11:10   │
│ Tech         │ 12   │ 1   │ 0        │ 29/5 17:45   │
└─────────────────────────────────────────────────────┘

Click row → group detail (action items + reminders + note).
```

Chi tiết entity reminder ở [§13](./13-reminders-tasks.md).

## 9.9 Tech stack web

- **Backend**: FastAPI, cùng process với bot
- **Templating**: Jinja2 server-side render
- **Interaction**: HTMX cho partial update (no full SPA)
- **Client state**: Alpine.js cho toggle/dropdown nhẹ
- **CSS**: Tailwind (utility-first)
- **Form**: HTML form + HTMX submit (no React)
- **Charts**: Chart.js trên Usage/Revenue page

Lý do: web admin scale nhỏ (1 sếp = 1 user, ít concurrent), không cần
SPA. HTMX = 1/5 code so với React. Sửa nhanh, dễ ship.

## 9.10 Đã chốt

- UI VN-only MVP. Toggle EN khi có user thực yêu cầu.
- Mobile-responsive qua Tailwind breakpoint. Không PWA.
- Design language: tham khảo Linear / Stripe Dashboard. Không emoji, không AI-themed copy.
