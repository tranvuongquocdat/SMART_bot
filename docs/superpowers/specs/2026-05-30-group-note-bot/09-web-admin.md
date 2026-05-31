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
/channels                — Connect Zalo / Telegram (xem bot acc nào đang được gán)
/plugins                 — Marketplace + manage installed
/plugins/:id             — Plugin detail (OAuth + settings form)
/usage                   — Token + cost dashboard
/settings/general        — Tên bot, ngôn ngữ, TZ, retention
/settings/ai             — Provider + model (smart/fast) + custom provider
/settings/account        — Email, đổi mật khẩu, đăng xuất
/subscription            — Gói + VietQR + lịch sử thanh toán
```

## 9.3 Sitemap (superadmin pages)

Chỉ visible khi `role=superadmin`:

```
/admin/bosses            — List + detail + set expiry + add payment + assign bot acc
/admin/bot-accounts      — Pool bot acc Zalo/Telegram: list, login/relogin, assign, traffic
/admin/bot-accounts/:id  — Detail: status, sessions, msgs in/out, assignment list
/admin/models            — Model registry CRUD (provider, model, tier, ctx, cost, is_default)
/admin/feature-routing   — Bảng feature → tier (edit live)
/admin/payments          — Log payment + [+ Add payment]
/admin/revenue           — Chart MRR / ARR / top customer
```

### `/admin/bot-accounts` chi tiết

```
┌────────────────────────────────────────────────────────────────┐
│ Bot accounts                                    [+ Thêm acc]   │
├────────────────────────────────────────────────────────────────┤
│ Provider │ Số/handle    │ Status        │ Sếp serve │ 7d msg in│
│ zalo     │ 0903xxx789   │ ● Active      │ 3         │ 1,247    │
│ zalo     │ 0905xxx101   │ ● Rate-limit  │ 2         │ 982      │
│ zalo     │ 0908xxx234   │ ● Logged-out  │ 0         │ 0        │
│ telegram │ @smart_bot   │ ● Active      │ 12        │ 4,109    │
└────────────────────────────────────────────────────────────────┘

Click row → Detail:
  - QR/cookie login flow (Zalo personal)
  - Force re-login button
  - Pause / Resume
  - List sếp đang được gán + [Reassign] per row
  - Counter: msg in/out tổng, msg 7d, latency reply trung bình
  - Log lỗi gần nhất
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

- **Note tab**: render note + Edit/Refresh/Export
- **History tab**: timeline version note + diff view
- **Action Items tab**: filter view của section "Việc đang mở"
- **Members tab**: list người gửi (display name), count message 7d

## 9.6 Channel wizard

Mỗi channel có flow guide ngắn. Hiển thị bot acc đã được superadmin gán:

```
/channels
  ┌─────────────────────────────────────────────┐
  │ Zalo                                         │
  │ Bot acc đã gán: 0903xxx789  [Connect Zalo]  │
  │                                              │
  │ (Chưa gán → "Liên hệ admin để được cấp acc") │
  └─────────────────────────────────────────────┘

[ Connect Zalo ]
  ↓
Modal: "Em sẽ mở Zalo, anh nhắn /start <token> cho bot ở 0903xxx789."
  ↓ Click "Tiếp"
Deep-link / copy số bot → Zalo app
  ↓ (Sếp tap Gửi message /start <token>)
Bot reply, web detect (poll hoặc Server-Sent Events)
  ↓
Channels page hiện "Đã kết nối"
```

Telegram tương tự với `https://t.me/<bot_acc>?start=<token>`.

## 9.7 Reminders & Projects

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

## 9.8 Tech stack web

- **Backend**: FastAPI, cùng process với bot
- **Templating**: Jinja2 server-side render
- **Interaction**: HTMX cho partial update (no full SPA)
- **Client state**: Alpine.js cho toggle/dropdown nhẹ
- **CSS**: Tailwind (utility-first)
- **Form**: HTML form + HTMX submit (no React)
- **Charts**: Chart.js trên Usage/Revenue page

Lý do: web admin scale nhỏ (1 sếp = 1 user, ít concurrent), không cần
SPA. HTMX = 1/5 code so với React. Sửa nhanh, dễ ship.

## 9.9 Đã chốt

- UI VN-only MVP. Toggle EN khi có user thực yêu cầu.
- Mobile-responsive qua Tailwind breakpoint. Không PWA.
- Design language: tham khảo Linear / Stripe Dashboard. Không emoji, không AI-themed copy.
