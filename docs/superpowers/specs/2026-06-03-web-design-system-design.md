# Web Design System & Frontend Foundation — Design Spec

**Ngày:** 2026-06-03
**Sub-project:** 1/4 trong nhánh redesign web (sau đây gọi tắt là **SP1**).
**Status:** draft, chờ duyệt.

## 1. Mục tiêu & phạm vi

### Mục tiêu
Dựng lại nền tảng frontend cho cả hai mặt web (admin dành cho boss/super-admin và web chat dành cho user) bằng một design system thống nhất, giải quyết các vấn đề trong `note.txt`:
- Giao diện hiện tại "rất xấu, nhất là admin", trông giả AI, thiếu chuyên nghiệp.
- Flow lủng củng, login bị "not logged in", không xoá được acc nhầm, không có droplist user, không thấy stats per bot account.
- Không có chuẩn chung để mỗi trang viết một kiểu.

### Phạm vi của SP1
- Dựng repo frontend mới (Vite + React + Tailwind + shadcn/ui) song song với backend FastAPI.
- Định nghĩa design tokens (màu, font, spacing, radii, shadow) cho cả light + dark mode, accent **xanh ngọc**.
- Cài + chuẩn hoá danh sách primitive từ shadcn/ui (button, dialog, dropdown, table, sheet, command, …) cộng với một số component dùng chung custom (AppShell, DataTable, UserPicker, EmptyState, StatusDot).
- Build pipeline tích hợp vào FastAPI: `vite build` xuất ra `src/web/static/app/`, FastAPI mount qua `StaticFiles` và catch-all cho SPA routing.
- Auth: tái sử dụng nguyên Google OAuth + session cookie hiện tại, fetch từ React dùng `credentials: 'include'`, CSRF token đọc từ cookie sẵn có ở `src/web/security.py`.
- Hai trang mẫu để validate hệ thống:
  - **Super-admin · Models & Bots** (quản lý 3 slot model mặc định + danh sách bot account Zalo/Telegram + phân bổ acc-cho-boss + message count 7 ngày).
  - **Boss · Group note viewer** (xem note 1 nhóm: tóm tắt AI, tab Tóm tắt/Dòng thời gian/Tác vụ/Nhắc lịch/Quyết định/Tệp & link, right panel stats + members + recent files).

### Ngoài phạm vi SP1
- Rewrite toàn bộ admin (12 trang) — đó là **SP2** với chiến lược **big-bang** (đã chốt).
- Redesign web test chat — **SP3**.
- UX flow fixes (login gate, xoá acc, droplist add group, fix VN typing gửi 2 message, nút open-admin-từ-test) — **SP4**, sẽ làm song song hoặc sau SP2.
- API rewrite cho mọi trang — chỉ port các endpoint cần cho 2 trang mẫu của SP1.

## 2. Stack & rationale

| Lựa chọn | Lý do |
|---|---|
| Vite + React (TypeScript) | DX nhanh, ecosystem shadcn/ui là React, đạt mức polish Linear/Vercel mà không phải viết tay từ đầu. Không cần SSR vì toàn bộ admin nằm sau login. |
| shadcn/ui | Các primitive đã được iterate nhiều lần, ra hộp đã đẹp; copy code vào repo nên không bị khoá vendor; tuỳ biến theme dễ qua CSS vars. |
| Tailwind CSS v4 | Đi cặp tự nhiên với shadcn/ui, lưới spacing nhất quán. |
| React Router v6 (data router) | Đủ cho SPA sau login; không cần Next.js SSR/RSC. |
| TanStack Query | Fetch + cache + invalidate gọn, dễ phối với CSRF + session cookie. |
| TanStack Table | Bảng có sort/filter/pagination, được wrap qua component `DataTable` dùng chung. |
| lucide-react | Bộ icon duy nhất. **Cấm dùng emoji** (⚡ 🚧 ✅ 📜) trong UI per note "trông rất dại". |
| pnpm | Package manager; reproducible, nhẹ. |

**Backend giữ nguyên FastAPI/Python**, chỉ thêm endpoint JSON dưới prefix `/api/v1/*` khi cần cho trang mới. Backend không bị viết lại trong SP1.

## 3. Repo layout

```
SMART_bot/
├── src/web/
│   ├── routes/                   # router cũ Jinja2 vẫn chạy
│   ├── routes_api/               # mới: JSON endpoints /api/v1/*
│   ├── static/app/               # ← vite build output (committed? no, build CI)
│   └── templates/                # Jinja2 cũ, gỡ dần theo SP2
└── frontend/                     # mới
    ├── package.json
    ├── pnpm-lock.yaml
    ├── vite.config.ts
    ├── tsconfig.json
    ├── tailwind.config.ts
    ├── postcss.config.js
    ├── index.html
    └── src/
        ├── main.tsx              # ReactDOM.createRoot + router
        ├── App.tsx               # router definition
        ├── routes/
        │   ├── _layout.tsx       # AppShell wrap
        │   ├── superadmin.models.tsx
        │   └── groups.$groupId.tsx
        ├── components/
        │   ├── ui/               # shadcn primitives (button, dialog, …)
        │   ├── app-shell.tsx     # sidebar + topbar + user dropdown
        │   ├── data-table.tsx
        │   ├── user-picker.tsx
        │   ├── empty-state.tsx
        │   ├── status-dot.tsx
        │   └── theme-toggle.tsx
        ├── features/
        │   ├── superadmin-models/
        │   └── group-notes/
        ├── lib/
        │   ├── api.ts            # fetch wrapper (credentials, csrf header)
        │   ├── auth.ts           # current-user query
        │   ├── theme.ts          # light/dark provider + localStorage
        │   └── format.ts
        └── styles/
            └── globals.css       # tailwind base + theme vars
```

**Build pipeline:**
- Dev: `pnpm dev` chạy Vite ở `:5173`, proxy `/api/*` → FastAPI `:8000`. Lập trình live-reload.
- Production: `pnpm build` → output thẳng vào `../src/web/static/app/`. FastAPI mount `StaticFiles(directory="src/web/static/app", html=True)` ở path `/app`, kèm một catch-all route trả `index.html` cho mọi sub-path để React Router hoạt động.
- CI: thêm bước `pnpm install --frozen-lockfile && pnpm build` trước khi build Docker image (hoặc step deploy).
- `src/web/static/app/` được gitignore; build output tạo lúc CI/deploy.

## 4. Auth model

- Giữ nguyên Google OAuth (`src/web/routes/auth.py`) + session cookie (HttpOnly, SameSite=Lax) + CSRF token đã có.
- Trang `index.html` của React app **không** chứa thông tin nhạy cảm. Trên load, app gọi `GET /api/v1/me`. Nếu 401, redirect về `/login` (route Jinja2 cũ — hoặc về sau port login sang React ở SP2). Nếu 200, render app.
- Mọi fetch dùng `credentials: 'include'`. Header `X-CSRF-Token` lấy từ cookie `csrf_token` cho các request thay đổi state (POST/PATCH/DELETE).
- Không lưu JWT, không lưu user info trong localStorage.

## 5. Design tokens

Theme switch light ↔ dark qua class `.light` trên `<html>` (mặc định dark; lưu chọn vào `localStorage.theme`). Tất cả token dùng HSL qua CSS vars theo convention shadcn/ui.

### Color (HSL)

| Token | Dark | Light | Mục đích |
|---|---|---|---|
| `--background` | `240 6% 7%` | `0 0% 100%` | Page bg |
| `--bg-subtle` | `240 6% 8.5%` | `240 10% 98.5%` | Thead, nested bg |
| `--foreground` | `0 0% 98%` | `240 10% 4%` | Body text |
| `--muted` | `240 4% 12%` | `240 5% 96%` | Subtle bg, chip |
| `--muted-foreground` | `240 5% 60%` | `240 4% 42%` | Secondary text |
| `--dim` | `240 4% 38%` | `240 4% 60%` | Tertiary text, icon |
| `--border` | `240 5% 14%` | `240 6% 92%` | Hairline gần như vô hình |
| `--border-strong` | `240 5% 18%` | `240 6% 86%` | Border khi hover hoặc dropdown |
| `--card` | `240 5% 9%` | `0 0% 100%` | Card surface |
| `--hover` | `240 5% 11%` | `240 5% 97%` | Row/item hover |
| `--primary` | `168 65% 55%` | `168 75% 32%` | Accent — **xanh ngọc** |
| `--primary-soft` | `168 50% 18%` | `168 60% 94%` | Background nhạt cho highlight |
| `--primary-foreground` | `170 80% 6%` | `white` | Text trên primary |
| `--danger` | `0 60% 60%` | `0 60% 50%` | Delete, error |
| `--ok` | `142 50% 55%` | `142 50% 40%` | Online, success |
| `--warn` | `38 88% 60%` | `38 88% 45%` | Warning |
| `--info` | `210 80% 65%` | `210 80% 50%` | Info, task tag |

Decision quan trọng: **chuyển từ indigo/violet (gợi ý ban đầu) sang xanh ngọc** theo yêu cầu trong brainstorm.

### Typography

- Font sans: **Inter Variable** (self-hosted hoặc qua `rsms.me`), bật `font-feature-settings: 'cv11','ss01','ss03'` để số gọn hơn.
- Font mono: **JetBrains Mono** cho UUID/handle/timestamp khi cần phân biệt.
- Base size **13.5px** (Linear-style, dense hơn 16px mặc định để chứa nhiều thông tin dashboard).
- Scale: 11/12/13/14/15/18/22/24/28 px.
- Heading letter-spacing `-0.025em`, body `1.55` line-height.
- Heading weight 600, body 400, label 500.

### Spacing, radii, motion

- Spacing: Tailwind default 4px step. Padding section 36–40px desktop, 24px mobile. Gap giữa các section 44px.
- Radii: `--radius: 8px`. Card 10–12px, button/input 6px, dialog 12px, brand mark 7px.
- Shadow rất tinh: `0 0 0 1px var(--border-strong), 0 1px 2px rgba(0,0,0,.3)` cho card. Modal/dropdown thì `0 12px 32px rgba(0,0,0,.4)`.
- Motion: chuyển trạng thái `transition: color 100ms, background 100ms`; collapse sidebar `240ms cubic-bezier(.4,0,.2,1)`. Không có spring bouncy.

### Iconography

- Chỉ dùng **lucide-react**, stroke-width 1.8.
- Status dùng `<StatusDot>` (chấm tròn 6px + halo nhẹ + label text màu khớp), không pill border.
- Brand mark "S" 26px, gradient teal → cyan, inner highlight + ring border.

## 6. Component primitives

Cài qua `pnpm dlx shadcn@latest add ...`:

```
button, input, textarea, label, select, dropdown-menu, command,
dialog, alert-dialog, sheet, tabs, table, card, badge, separator,
tooltip, skeleton, sonner (toast), avatar, checkbox, switch
```

Custom thêm trong `components/`:

| Component | Vai trò |
|---|---|
| `<AppShell>` | Sidebar collapsible (232px ↔ 60px) + topbar sticky (backdrop-blur) + nút theme + user dropdown ở đáy sidebar (avatar + name + role + menu Hồ sơ/Cài đặt/Đăng xuất). Mobile (<900px) sidebar thành drawer với scrim. |
| `<DataTable>` | Wrap TanStack Table, bao gồm sort/filter/pagination, row hover, header sticky, mobile auto-switch sang card list (mỗi cell xuống dòng có label uppercase). |
| `<UserPicker>` | Combobox async (shadcn `command` + popover) chọn user theo tên/handle. Dùng cho "add group" thay vì input free-text. |
| `<EmptyState>` | Icon lucide + title + desc + CTA. Không emoji. |
| `<StatusDot>` | 6px chấm, halo 3px nhẹ, color theo status. Đi kèm text optional. |
| `<ThemeToggle>` | Một nút bóng đèn — outline khi dark, fill vàng khi light — bấm toggle class `.light`. |

## 7. Hai trang mẫu

### 7.1 Super-admin · Models & Bots

Route: `/app/superadmin/models`. Quyền: super-admin only (guard ở route loader: gọi `/api/v1/me` rồi check role).

Layout:
- `AppShell` với nav-section "Super-admin" active item "Models & Bots".
- Breadcrumb: Super-admin / **Models & Bots**.
- Page head: title "Models & Bots" + sub-text.
- Tabs: Default models / Bot accounts / Providers & keys.
- Section "Model slots" (3 cards Smart/Fast/Vision): mỗi card có icon, label uppercase, model name, provider + mô tả ngắn, status dot, link "Đổi". Trạng thái "Chưa cấu hình" có warning dot + CTA "Thiết lập".
- Section "Bot accounts" (DataTable): cột Account (tên + handle mono), Kênh (chip), Phân bổ, Tin nhắn 7d (số bold + mô tả), Trạng thái (status dot), action menu ⋯.
- CTA primary "+ Kết nối account" góc phải section.

API mới cần cho trang này:
- `GET /api/v1/superadmin/model-slots` → `[{slot, model, provider, status}]`
- `PATCH /api/v1/superadmin/model-slots/:slot` → đổi model
- `GET /api/v1/superadmin/bot-accounts?range=7d` → list bot accounts với stats
- `POST /api/v1/superadmin/bot-accounts` → tạo connection (placeholder, full flow ở SP sau)
- `PATCH /api/v1/superadmin/bot-accounts/:id` → cập nhật assigned_to
- `DELETE /api/v1/superadmin/bot-accounts/:id` → xoá (đáp ứng note "ko xoá được acc tạo nhầm")

### 7.2 Boss · Group note viewer

Route: `/app/groups/:groupId`. Quyền: boss owner của group đó.

Layout:
- `AppShell` với nav-section "Workspace" active item "Groups".
- Breadcrumb: Groups / **Phòng Kinh Doanh**.
- Group header: avatar 52px (gradient theo group), tên + chip kênh (Zalo/Telegram/Lark), meta (số member, msg/30d, hoạt động cuối), actions "Xuất" + "Cấu hình nhóm".
- Tabs với counter: Tóm tắt / Dòng thời gian / Tác vụ (n) / Nhắc lịch (n) / Quyết định (n) / Tệp & link.
- Two-column grid (1fr 320px):
  - **Trái**:
    - Summary card với accent-bar trái, tóm tắt AI cho hôm nay, từ khoá highlight bằng `--primary-soft`.
    - "Mục được trích xuất hôm nay" — list item có check, text, tag (Tác vụ/Nhắc lịch/Quyết định) màu khác nhau, assignee, deadline, timestamp gốc.
    - Timeline preview (5–10 msg gần nhất): mỗi msg có avatar (boss gradient tím, bot gradient teal, member solid muted), tên + thời gian, body text, badge "Đã trích: X tác vụ" cho msg đã được extract.
  - **Phải** (sticky `top: 90px`): card 7-day stats (4 metric với trend), card members (avatar gradient + name + role + status dot), card tệp & link gần đây.
- Mobile: right panel rơi xuống dưới timeline, single column.

API mới cần:
- `GET /api/v1/groups/:groupId` → meta nhóm
- `GET /api/v1/groups/:groupId/summary?date=today` → tóm tắt AI
- `GET /api/v1/groups/:groupId/items?date=today&type=*` → action items
- `GET /api/v1/groups/:groupId/timeline?cursor=...` → message timeline với extract markers
- `GET /api/v1/groups/:groupId/stats?range=7d` → 4 metric
- `GET /api/v1/groups/:groupId/members` → list member với online status
- `GET /api/v1/groups/:groupId/files?limit=10` → files & links

Các endpoint này wrap lại trạng thái đã có trong DB hiện tại; SP1 chỉ port để hai trang sample chạy được với data thật, không thay đổi schema.

## 8. Responsive

Cả hai trang đều **mobile-first thực sự** vì boss xem nhiều qua mobile. Breakpoint:

- `< 600px`: padding 18px, sidebar hidden, drawer mở qua hamburger.
- `< 720px`: table → card list (cell display block, label uppercase).
- `< 900px`: sidebar trở thành overlay drawer, layout right-panel xuống dưới.
- `≥ 900px`: layout 2 cột.
- `≥ 1024px`: padding 36–40px.

## 9. Testing & Definition of Done cho SP1

**Tự động:**
- Lint (`pnpm lint`) + typecheck (`pnpm tsc --noEmit`) pass.
- Build (`pnpm build`) ra `src/web/static/app/` không lỗi.
- 1 Playwright test smoke: load `/app/superadmin/models` đã login → thấy "Models & Bots" + ít nhất 1 bot account row.
- 1 Playwright test smoke: load `/app/groups/<seed-id>` → thấy tên group + summary card render.

**Thủ công (Definition of Done):**
- Chạy `pnpm dev`, login, mở 2 trang sample, toggle theme — không có lỗi console, transition mượt.
- Resize ↔ 360px / 768px / 1280px — không vỡ layout, table convert thành card đúng.
- Sidebar collapse/expand, drawer mobile, user dropdown — đều hoạt động.
- Lighthouse desktop ≥ 90 cho Performance + Accessibility (sau login).
- FastAPI vẫn chạy bình thường, mọi route Jinja2 cũ không bị ảnh hưởng (regression check 1 vòng login → dashboard cũ).

## 10. Migration outlook (post-SP1)

SP1 chỉ build foundation + 2 page mẫu. SP2 sẽ big-bang rewrite toàn bộ admin (12 trang) dựa trên design system này. Trình tự port sẽ định nghĩa trong SP2 spec (riêng), không gộp vào đây.

## 11. Risks & open questions

| Risk | Mitigation |
|---|---|
| Build pipeline mới làm pipeline deploy phức tạp hơn | Document trong README; thêm step `pnpm build` vào CI rõ ràng; gitignore `static/app/` để tránh commit nhầm output. |
| Auth cookie không gửi qua khi dev (cross-origin :5173 → :8000) | Cấu hình Vite proxy `/api` để cùng origin; hoặc set CORS `allow_credentials=True` + `allow_origins=['http://localhost:5173']` chỉ ở dev. |
| Dùng song song Jinja2 cũ + React mới ở 2 namespace dễ gây xung đột session | Đảm bảo cookie path = `/`; session reader giống nhau cho cả `/api/v1/*` và `/` cũ. |
| Big-bang SP2 có thể vỡ trang nào đó nếu thiếu API | SP1 xong sẽ làm 1 audit map từng trang Jinja2 → endpoint cần có; là bước mở đầu của SP2. |

Open: tên brand "S" trong brand mark có phải logo cuối cùng không? (placeholder hiện tại, không chặn SP1).
