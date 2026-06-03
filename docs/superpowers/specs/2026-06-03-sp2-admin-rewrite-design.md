# SP2 — Admin Rewrite Big-Bang Spec

**Ngày:** 2026-06-03
**Status:** draft → exec ngay sau khi user OK.
**Tiền đề:** SP1 đã build xong foundation. Stack/design/RBAC/module pattern locked. Spec này CHỈ liệt kê những gì SP2 thêm mới.

## 1. Mục tiêu

Port toàn bộ admin Jinja2 (13 trang boss + 11 trang super-admin + login) sang React module pattern đã thiết lập ở SP1. Sau SP2:
- Xoá hẳn `/legacy-app/*`.
- Tất cả surface admin chạy trong `frontend/`.
- Login chạy bằng React (hiện tại Jinja2).
- 4 bảng DB còn thiếu được tạo qua migration để feature group note thật sự dùng được.

## 2. Schema migrations (4)

Tạo file mới trong `migrations/` (alembic). Mỗi migration là một file riêng để rollback dễ.

| Bảng | Cột chính | Index |
|---|---|---|
| `group_members` | `id PK`, `group_id FK group_notes.id`, `display_name TEXT`, `external_id TEXT`, `role TEXT`, `last_seen_at TIMESTAMPTZ`, `joined_at TIMESTAMPTZ DEFAULT now()` | `(group_id)`, `UNIQUE(group_id, external_id)` |
| `group_summaries` | `id PK`, `group_id FK`, `date_label TEXT`, `body TEXT`, `model TEXT`, `tokens INT`, `updated_at TIMESTAMPTZ` | `(group_id, date_label)`, `(updated_at DESC)` |
| `decisions` | `id PK`, `group_id FK`, `text TEXT`, `decided_by TEXT`, `source_message_id BIGINT`, `created_at TIMESTAMPTZ DEFAULT now()` | `(group_id, created_at DESC)` |
| `group_artifacts` | `id PK`, `group_id FK`, `kind TEXT CHECK kind IN ('doc','link','image','video')`, `name TEXT`, `url TEXT`, `source_message_id BIGINT`, `created_at TIMESTAMPTZ DEFAULT now()` | `(group_id, created_at DESC)` |

Sau migration: SP1 endpoint `/api/v1/admin/groups/:id/{members,summary,files}` thay vì return empty shapes sẽ trả data thật khi có. Endpoint không cần đổi contract.

**Không** tạo seed data trong migration. Để empty cũng OK; module group note có graceful empty state.

## 3. JSON API endpoints mới

Tất cả prefix `/api/v1/admin/*` (Boss + Superadmin) hoặc `/api/v1/superadmin/*` (Superadmin only). Mỗi endpoint kèm `Depends(require_boss)` hoặc `Depends(require_superadmin)`. Đa số là wrap lại logic đã có trong `src/web/routes/{app.py,admin.py}`.

### Boss-facing
| Method + Path | Source |
|---|---|
| `GET /api/v1/admin/dashboard` | `app.py:dashboard_view` → JSON {recent_groups, today_items, stats_30d} |
| `GET /api/v1/admin/groups` | `app.py:groups_list` → JSON list |
| `POST /api/v1/admin/groups` | tạo group |
| `POST /api/v1/admin/groups/:id/members` | thêm member (dùng UserPicker) |
| `DELETE /api/v1/admin/groups/:id/members/:mid` | xoá member |
| `GET /api/v1/admin/reminders` | `app.py:reminders_view` |
| `POST /api/v1/admin/reminders` | tạo |
| `PATCH /api/v1/admin/reminders/:id` | đổi (snooze, done) |
| `DELETE /api/v1/admin/reminders/:id` | xoá |
| `GET /api/v1/admin/projects` | list |
| `POST /api/v1/admin/projects` | tạo |
| `GET /api/v1/admin/action-items?group_id&project_id&done` | filter |
| `PATCH /api/v1/admin/action-items/:id` | toggle done |
| `GET /api/v1/admin/channels` | list connected channels |
| `POST /api/v1/admin/channels/:provider/connect` | start OAuth/connect flow |
| `DELETE /api/v1/admin/channels/:id` | disconnect |
| `GET /api/v1/admin/usage?range=30d` | usage stats |
| `GET /api/v1/admin/subscription` | plan + billing |
| `GET /api/v1/admin/settings/account` | profile |
| `PATCH /api/v1/admin/settings/account` | update profile |
| `GET /api/v1/admin/settings/ai` | 3 slot model + BYO keys (mask secrets) |
| `PATCH /api/v1/admin/settings/ai` | đổi slot / lưu key |
| `POST /api/v1/admin/settings/ai/test` | test 1 key |
| `GET /api/v1/admin/settings/general` | org settings |
| `PATCH /api/v1/admin/settings/general` | update |

### Super-admin
| Method + Path | Source |
|---|---|
| `GET /api/v1/superadmin/bosses` + `POST` + `DELETE /:id` | quản lý boss accounts |
| `GET /api/v1/superadmin/bot-accounts` (mở rộng từ SP1) + `POST` connect + `DELETE` |  |
| `GET /api/v1/superadmin/models` + `PATCH /:id` | mở rộng từ SP1 model-slots |
| `GET /api/v1/superadmin/prompts` + `POST` + `GET /:id` + `PATCH /:id` |  |
| `GET /api/v1/superadmin/note-templates` + CRUD |  |
| `GET /api/v1/superadmin/agent-triggers` + CRUD | cron/event triggers |
| `GET /api/v1/superadmin/audit-log?cursor&limit` | read-only paginated |
| `GET /api/v1/superadmin/feature-budgets` + `PATCH` | cost caps |
| `GET /api/v1/superadmin/llm-routes` + `PATCH` | route mapping |
| `GET /api/v1/superadmin/retrieval-pipelines` + `PATCH` | RAG config |

Tất cả wrap logic đã có trong `src/web/routes/admin.py` — chỉ đổi format response từ TemplateResponse → JSONResponse, đổi form POST → JSON body, giữ nguyên DB query.

## 4. Frontend module pages

Mỗi page là 1 file `frontend/src/modules/{admin,superadmin}/features/<feature>/<name>.tsx`. Mỗi feature folder có `api.ts` (query/mutation) + page + sub-components.

### Module admin (boss-facing) — 13 pages
```
admin/features/
├── dashboard/page.tsx
├── groups/list-page.tsx (replace SP1 stub)
├── groups/group-detail.tsx (already SP1)
├── reminders/page.tsx
├── projects/page.tsx
├── action-items/page.tsx
├── channels/page.tsx
├── usage/page.tsx
├── subscription/page.tsx
├── settings/account-page.tsx
├── settings/ai-page.tsx
├── settings/general-page.tsx
```

Settings nằm chung folder, 3 sub-page chọn qua sidebar settings hoặc tabs. Quyết định: dùng tabs ngang ở đầu trang Settings (1 trang `settings/index.tsx` có tabs Account / AI / General).

### Module superadmin (11 pages)
```
superadmin/features/
├── models/page.tsx (replace SP1 placeholder; merge bots+models+llm-routes+budgets)
├── bosses/page.tsx
├── bot-accounts/page.tsx (mở rộng SP1 table — add connect/delete + per-acc detail panel)
├── prompts/list-page.tsx + prompts/detail-page.tsx
├── note-templates/page.tsx
├── agent-triggers/page.tsx
├── audit-log/page.tsx
├── feature-budgets/page.tsx
├── llm-routes/page.tsx
├── retrieval-pipelines/page.tsx
```

Nav update: cả `modules/admin/nav.ts` và `modules/superadmin/nav.ts` thay link "/coming-soon" stub bằng đường thật. Bỏ `<ComingSoon>` cho các trang đã build (giữ component nếu trang nào mới phát sinh).

## 5. Login port to React

Tạo `frontend/src/routes/login.tsx` (route ngoài 2 module, không cần RBAC loader). Cần:
- Email + password form (backend đã có POST /login)
- Google OAuth button (link tới `/api/oauth/google/start`)
- Sau login thành công → backend đã set session cookie + redirect 303 → server-side redirect tới `/app` → React `requireAuth` xử lý lấy /me và chuyển vào module đúng

Xoá `src/web/templates/login.html` sau khi React login chạy.

## 6. Cleanup sau khi tất cả page port xong

- Xoá hẳn `src/web/routes/app.py` (Jinja2 boss-facing)
- Xoá hẳn `src/web/routes/admin.py` (Jinja2 super-admin)
- Xoá `src/web/templates/{dashboard,groups,group_detail,reminders,_reminders_list,projects,action_items,channels,usage,subscription,settings_*,login}.html`
- Xoá `src/web/templates/admin/*`
- Xoá `app.include_router(web_app.router, prefix="/legacy-app")` trong `src/main.py`
- Xoá `src/web/static/app.js + style.css` (Jinja2 frontend assets)
- Update tests đã reference `/legacy-app/*` → reference các JSON endpoint mới hoặc xoá nếu chỉ test rendering Jinja2

## 7. Testing & DoD

**Tự động:**
- Pytest 220+ tests vẫn pass (regression).
- Mỗi endpoint mới TDD'd với 2 test: auth gating + happy path.
- `frontend/pnpm build` + `tsc --noEmit` clean.
- Playwright smoke mở rộng: 1 test/feature group cho boss + superadmin (smoke render + nav).

**Thủ công (DoD):**
- Login → dashboard render với data thật.
- Tạo + xoá reminder/project/group/bot-account → success.
- Đổi settings/ai 3 slot → reload thấy giữ giá trị.
- Mobile responsive cho 2-3 trang đại diện.
- Click qua mọi nav item, không có "Coming soon" stub trên trang đã port.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Logic biz ở `app.py`/`admin.py` phức tạp, dễ miss feature khi port | Mỗi PR / commit kèm reference Jinja2 route + 1-2 sentence "behavior reproduced" |
| Schema migrations đụng prod data | Migrations chỉ ADD (additive), không ALTER existing. Test rollback. |
| Form submission UX khác giữa Jinja2 (full page reload) và React (mutate + invalidate query) | Mỗi mutation viết kèm `toast()` báo success/error |
| 25 trang nhiều, dễ inconsistent | Reuse `<DataTable>`, `<EmptyState>`, `<UserPicker>`, `<ComingSoon>` từ SP1; mọi form dùng `<Input>` + `<Label>` + `<Button>` shadcn — không tự CSS button mới |
| Login port có thể vỡ existing OAuth flow | Test thủ công full flow (Google login → redirect → land in app) trước khi xoá Jinja2 login |

## 9. Order of execution (priority sorted)

1. Schema migrations (4 file) — pre-requisite.
2. Backend JSON API mở rộng theo nhóm: settings → groups → reminders → projects → action-items → channels → usage+subscription → superadmin (bot-accounts → models → bosses → prompts → note-templates → agent-triggers → audit-log → feature-budgets → llm-routes → retrieval-pipelines).
3. Frontend page batches tương ứng (port song song với endpoint).
4. Login port to React.
5. Cleanup (xoá legacy-app + Jinja2 templates).
6. Final smoke + Playwright update.
