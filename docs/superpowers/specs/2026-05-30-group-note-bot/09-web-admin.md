[← Index](./README.md)

# §9. Web admin

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
/digests                 — (Phase 1, MVP show "Coming soon")
/channels                — Connect Zalo / Telegram / Lark Messenger
/plugins                 — Marketplace + manage installed
/plugins/:id             — Plugin detail (OAuth + settings form)
/usage                   — Token + cost dashboard
/settings/general        — Tên bot, ngôn ngữ, TZ, retention
/settings/ai             — Provider + model + custom provider
/settings/account        — Email, đổi mật khẩu, đăng xuất
/subscription            — Gói + VietQR + lịch sử thanh toán
```

## 9.3 Sitemap (superadmin pages)

Chỉ visible khi `role=superadmin`:

```
/admin/bosses            — List + detail + set expiry + add payment
/admin/payments          — Log payment + [+ Add payment]
/admin/revenue           — Chart MRR / ARR / top customer
```

## 9.4 Dashboard widgets

```
┌────────────┬────────────┬────────────┬────────────┐
│ N groups   │ K open     │ Digest:    │ Tháng này  │
│ across M   │ action     │ (Coming    │ $X /       │
│ channels   │ items      │  soon)     │ Y M tok    │
└────────────┴────────────┴────────────┴────────────┘
┌──────────────────────────┬──────────────────────────┐
│ Hoạt động 7 ngày qua     │ Cảnh báo                 │
│ [bar chart messages/day] │ • Zalo OA token sắp hết  │
│                          │ • 3 task quá hạn         │
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

Mỗi channel có flow guide ngắn:

```
/channels → [ Connect Zalo ]
  ↓
Modal: "Em sẽ mở Zalo, bot tự DM anh. Anh chỉ tap Gửi."
  ↓ Click "Tiếp"
Deep-link → Zalo app
  ↓ (Sếp tap Gửi message /start <token>)
Bot reply, web detect (poll hoặc Server-Sent Events)
  ↓
Channels page hiện ✓
```

Telegram & Lark Messenger tương tự (URL scheme khác).

## 9.7 Tech stack web

- **Backend**: FastAPI, cùng process với bot
- **Templating**: Jinja2 server-side render
- **Interaction**: HTMX cho partial update (no full SPA)
- **Client state**: Alpine.js cho toggle/dropdown nhẹ
- **CSS**: Tailwind (utility-first)
- **Form**: HTML form + HTMX submit (no React)
- **Charts**: Chart.js trên Usage/Revenue page

Lý do: web admin scale nhỏ (1 sếp = 1 user, ít concurrent), không cần
SPA. HTMX = 1/5 code so với React. Sửa nhanh, dễ ship.

## 9.8 Mở

- **(mở) i18n** — UI tiếng Việt mặc định. Toggle EN có cần? MVP chỉ VN.
- **(mở) Mobile-responsive** — Tailwind breakpoint đủ, không PWA.
