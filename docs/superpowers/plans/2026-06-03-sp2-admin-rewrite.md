# SP2 — Admin Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Port all admin/superadmin Jinja2 pages to React + add 4 missing schema tables, then delete legacy.

**Architecture:** Reuse SP1 module pattern. Each page = a feature folder under `modules/{admin,superadmin}/features/<name>/`. Each backend endpoint = TDD'd JSON route wrapping existing Jinja2 logic.

**Tech Stack:** SP1 inherited — Vite + React + TS + shadcn/ui + Tailwind + TanStack Query/Table, FastAPI + asyncpg + alembic + pytest.

**Reference:** Spec `docs/superpowers/specs/2026-06-03-sp2-admin-rewrite-design.md`. SP1 plan `docs/superpowers/plans/2026-06-03-web-frontend-foundation.md`.

---

## Conventions for this plan (apply to every page task)

- **Reuse SP1 primitives**: `<AppShell>` (already wired via module layout), `<DataTable>`, `<UserPicker>`, `<EmptyState>`, `<StatusDot>`, `<ThemeToggle>`. Don't reinvent. If you need a new primitive, name it and place in `components/`.
- **Module structure per page**:
  ```
  modules/<m>/features/<feature>/
  ├── api.ts          # queryOptions + mutationFn
  ├── page.tsx        # the route component
  └── <sub-comp>.tsx  # optional supporting components
  ```
- **Backend pattern per endpoint**:
  - File: `src/web/routes/api_admin.py` (boss) or `src/web/routes/api_superadmin.py` (superadmin) — append, don't create per-feature files unless they grow past ~300 lines.
  - Gated by `Depends(require_boss)` or `Depends(require_superadmin)`.
  - GET = no CSRF. POST/PATCH/DELETE inherit FastAPI CSRF? — actually the existing `verify_csrf` is form-based; for JSON we rely on the SameSite=Lax cookie + X-CSRF-Token header sent by `lib/api.ts`. Make sure JSON mutations DO NOT use the form-based `verify_csrf` decorator from Jinja2 routes; check the `X-CSRF-Token` header against `request.cookies.get(CSRF_COOKIE)` manually OR add a new dep `verify_json_csrf` in `src/web/security.py` and use it.
  - Source of truth for biz logic: copy from Jinja2 route in `src/web/routes/app.py` (boss) or `src/web/routes/admin.py` (superadmin). Reference the line range in your commit msg.
- **Tests per endpoint** (TDD):
  - 1 test for auth gating (boss → 403 on superadmin, or unauth → 401).
  - 1 test for happy path (GET returns expected shape, POST/PATCH mutates DB).
  - Use existing fixtures in `tests/conftest.py`.
- **Page rendering checkpoint**: every page task ends with `cd frontend && pnpm build && pnpm tsc --noEmit` clean.
- **Commit per task** with conventional commit msg.

---

## Phase A — Schema migrations (1 task)

### Task SP2-1: Add 4 missing tables

**Files:**
- Create: `migrations/versions/<rev>_add_group_metadata_tables.py`

- [ ] **Step 1: Identify migration tool + latest revision**

```bash
ls migrations/versions/ | tail -5
cat migrations/env.py | head -10  # confirm it's alembic
```

Use the latest revision as `down_revision`.

- [ ] **Step 2: Write the migration**

Create alembic migration with the 4 tables per spec section 2. Use `op.create_table(...)`. Each table additive. Don't `DROP` anything. PK = `id BIGSERIAL`. All FK references `group_notes.id` with `ON DELETE CASCADE`.

```python
"""add group_members + group_summaries + decisions + group_artifacts

Revision ID: <gen>
Revises: <previous>
"""

from alembic import op
import sqlalchemy as sa

revision = '<gen>'
down_revision = '<previous>'

def upgrade() -> None:
    op.create_table('group_members',
        sa.Column('id', sa.BigInteger, primary_key=True),
        sa.Column('group_id', sa.BigInteger, sa.ForeignKey('group_notes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('display_name', sa.Text, nullable=False),
        sa.Column('external_id', sa.Text),
        sa.Column('role', sa.Text),
        sa.Column('last_seen_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('joined_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('group_id', 'external_id', name='uq_group_members_external'),
    )
    op.create_index('ix_group_members_group_id', 'group_members', ['group_id'])

    op.create_table('group_summaries',
        sa.Column('id', sa.BigInteger, primary_key=True),
        sa.Column('group_id', sa.BigInteger, sa.ForeignKey('group_notes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('date_label', sa.Text, nullable=False),
        sa.Column('body', sa.Text),
        sa.Column('model', sa.Text),
        sa.Column('tokens', sa.Integer),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_group_summaries_group_date', 'group_summaries', ['group_id', 'date_label'])

    op.create_table('decisions',
        sa.Column('id', sa.BigInteger, primary_key=True),
        sa.Column('group_id', sa.BigInteger, sa.ForeignKey('group_notes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('decided_by', sa.Text),
        sa.Column('source_message_id', sa.BigInteger),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_decisions_group', 'decisions', ['group_id', sa.text('created_at DESC')])

    op.create_table('group_artifacts',
        sa.Column('id', sa.BigInteger, primary_key=True),
        sa.Column('group_id', sa.BigInteger, sa.ForeignKey('group_notes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.Text, nullable=False),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('url', sa.Text),
        sa.Column('source_message_id', sa.BigInteger),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('doc','link','image','video')", name='ck_group_artifacts_kind'),
    )
    op.create_index('ix_group_artifacts_group', 'group_artifacts', ['group_id', sa.text('created_at DESC')])

def downgrade() -> None:
    op.drop_table('group_artifacts')
    op.drop_table('decisions')
    op.drop_table('group_summaries')
    op.drop_table('group_members')
```

If `group_notes` is the right parent table name — verify with `grep -l "group_notes" migrations/versions/`. If FK target differs, adapt.

- [ ] **Step 3: Apply locally + verify tests**

```bash
alembic upgrade head
pytest tests/ -x -q 2>&1 | tail -5
```

Expected: migration succeeds, all 220 tests still pass.

- [ ] **Step 4: Replace empty-shape responses in `api_admin.py`**

Endpoints `/groups/:id/{members,summary,files}` and the `decisions` count in `/stats` currently return empty / 0. Replace with real queries on the new tables. Keep the same return contract.

- [ ] **Step 5: Update SP1 tests if needed**

If `tests/integration/test_api_admin_groups.py` had assertions that depended on empty `[]`, update to be more lenient (`isinstance(result, list)`).

- [ ] **Step 6: Commit**

```bash
git add migrations/ src/web/routes/api_admin.py tests/integration/test_api_admin_groups.py
git commit -m "feat(db): add group_members + group_summaries + decisions + group_artifacts tables"
```

---

## Phase B — JSON CSRF helper (1 task, prerequisite for all mutations)

### Task SP2-2: Add `verify_json_csrf` dep

**Files:**
- Modify: `src/web/security.py`
- Create: `tests/integration/test_json_csrf.py`

- [ ] **Step 1: Test first (TDD)**

`tests/integration/test_json_csrf.py`:

```python
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_json_post_without_csrf_header_rejected(client, logged_in_boss):
    # Use any /api/v1/admin/* POST endpoint once it exists; for now,
    # smoke a placeholder that the dep is registered correctly.
    pass  # filled in once first mutation endpoint lands; see Task SP2-3
```

- [ ] **Step 2: Implement `verify_json_csrf`**

In `src/web/security.py` append:

```python
async def verify_json_csrf(request: Request) -> None:
    """For JSON API mutation endpoints. Checks X-CSRF-Token header
    against the smart_csrf cookie. Safe methods skip."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token or cookie_token != header_token:
        raise HTTPException(status_code=403, detail="invalid csrf token")
```

Make sure `verify_csrf` (Jinja2 form-based) stays — they're separate.

- [ ] **Step 3: Commit**

```bash
git add src/web/security.py tests/integration/test_json_csrf.py
git commit -m "feat(security): verify_json_csrf dep for SPA mutation endpoints"
```

---

## Phase C — Settings (1 task — 3 sub-pages in 1 module)

### Task SP2-3: Settings module (account + AI + general)

**Files:**
- Backend (append to `src/web/routes/api_admin.py`):
  - GET/PATCH `/api/v1/admin/settings/account`
  - GET/PATCH `/api/v1/admin/settings/ai`
  - POST `/api/v1/admin/settings/ai/test`
  - GET/PATCH `/api/v1/admin/settings/general`
- Tests: `tests/integration/test_api_settings.py` (2 tests per endpoint = 8 tests)
- Frontend:
  - `frontend/src/modules/admin/features/settings/api.ts`
  - `frontend/src/modules/admin/features/settings/page.tsx` (wrapper with tabs)
  - `frontend/src/modules/admin/features/settings/account-tab.tsx`
  - `frontend/src/modules/admin/features/settings/ai-tab.tsx`
  - `frontend/src/modules/admin/features/settings/general-tab.tsx`
- Route: replace `<ComingSoon feature="Settings" />` in `modules/admin/routes.tsx` with the real page.
- Source Jinja2: `src/web/routes/app.py` search for `settings_account`, `settings_ai`, `settings_general` handlers; the templates `src/web/templates/settings_*.html` show the form shape.

Implementation guideline: 1 page component renders a header + 3 tabs (Account / AI / General) inside `<Tabs>`. Each tab consumes its query + has its own mutation form.

For Settings/AI specifically: 3 model slot cards (reuse `<SlotCard>` from SP1) but per-boss override of the system defaults. Plus BYO API key inputs (mask with password type, never echo back the full key from server — server returns `last_4` only). PATCH submits only the changed fields.

Test pattern (TDD): each endpoint gets 2 tests (auth + happy path). Mutation tests assert DB state changed.

Commit msg: `feat(settings): API + React module (account, AI 3-slot, general)`

---

## Phase D — Groups + Reminders + Projects + Action items (4 tasks)

### Task SP2-4: Groups list page + create/delete

Backend: GET/POST `/api/v1/admin/groups`, DELETE `/api/v1/admin/groups/:id`, POST `/api/v1/admin/groups/:id/members` (uses `<UserPicker>` with /api/v1/admin/people endpoint added en-route), DELETE `/api/v1/admin/groups/:id/members/:mid`.

Frontend: replace `<list-page.tsx>` stub with real list (table + create dialog using `<Dialog>`). When user picks a group → navigate to `/app/admin/groups/:id` (SP1 group-detail).

Source Jinja2: `src/web/routes/app.py:groups_list` + `src/web/templates/groups.html`.

Note: `/api/v1/admin/people` endpoint = `GET /api/v1/admin/people?q=...` returns list of users for `UserPicker` autocomplete (search across boss workspace).

Commit: `feat(groups): list page + member management API/UI`

### Task SP2-5: Reminders

Backend: GET/POST/PATCH/DELETE `/api/v1/admin/reminders`.
Frontend: `modules/admin/features/reminders/{api.ts,page.tsx,create-dialog.tsx,reminder-row.tsx}`. Replace nav stub.
Source Jinja2: `app.py:reminders_view` + `templates/reminders.html` + `_reminders_list.html`.
List items: `<DataTable>` with row actions (snooze button, mark-done checkbox, delete). Create dialog: text input + due_at date picker (shadcn doesn't have a native date picker — use native `<input type="datetime-local">` for SP2; fancier picker in SP3).

Commit: `feat(reminders): module page + API CRUD`

### Task SP2-6: Projects + action items

Backend: GET/POST `/api/v1/admin/projects`, GET/PATCH `/api/v1/admin/action-items`.
Frontend: 2 sibling pages `projects/page.tsx`, `action-items/page.tsx`. Projects list is simple (name + count). Action items page has filters (group, project, done) + checkbox to toggle done.
Source Jinja2: `app.py:projects_*`, `app.py:action_items_*`.
Replace 2 nav stubs.

Commit: `feat(projects+items): pages + API CRUD`

### Task SP2-7: Channels + Usage + Subscription (3 simple pages, 1 task)

Backend: GET `/api/v1/admin/channels`, POST `/api/v1/admin/channels/:provider/connect`, DELETE `/api/v1/admin/channels/:id`, GET `/api/v1/admin/usage?range=30d`, GET `/api/v1/admin/subscription`.

Frontend: 3 simple read-mostly pages.
- Channels: list of connected provider accounts (zalo/telegram/lark), with "Connect" buttons that redirect to OAuth/QR flow (backend handles).
- Usage: stats (messages/cost/tokens per day chart). Use `recharts` library — `pnpm add recharts` if needed.
- Subscription: current plan + billing status (likely read-only stub if no billing yet — show plan name + "Liên hệ admin" CTA).

Source Jinja2: `app.py:channels_view, usage_view, subscription_view` + templates.

Commit: `feat(channels+usage+sub): 3 pages + API`

---

## Phase E — Super-admin pages (5 tasks)

### Task SP2-8: Models management (replace SP1 ModelsPage with full CRUD)

Backend: extend `/api/v1/superadmin/model-slots` to support PATCH per slot. Add GET/POST/DELETE `/api/v1/superadmin/models` for the underlying `models` table (lower-level than slots). Add `/api/v1/superadmin/llm-routes` GET/PATCH + `/api/v1/superadmin/feature-budgets` GET/PATCH.

Frontend: enrich existing `modules/superadmin/features/models/page.tsx`. Add tabs: "Slots" (existing slot cards) / "Models" (CRUD table) / "Routes" (which feature uses which slot) / "Budgets" (cost cap per feature). Each tab = a sub-component.

Source: `src/web/routes/admin.py` — search for `models`, `llm_routes`, `feature_budgets`.

Commit: `feat(superadmin): models full CRUD + routes + budgets`

### Task SP2-9: Bot accounts management (expand SP1)

Backend: enrich `/api/v1/superadmin/bot-accounts` with POST/PATCH/DELETE + per-account detail (`/api/v1/superadmin/bot-accounts/:id/messages?limit=50`).

Frontend: `modules/superadmin/features/bot-accounts/page.tsx`. List view (already in SP1 ModelsPage as a section — move to standalone page). Add "Connect" wizard (Dialog with steps), "Delete" action with confirm AlertDialog (fixes user note "ko xoá được acc tạo nhầm"), "Assign to boss" via UserPicker, "View recent messages" expandable.

Update SP1 ModelsPage to remove the bot accounts section (now on its own page); replace with link "Quản lý bot accounts →".

Source: `admin.py:bot_accounts_*` + `templates/admin/bot_accounts.html`.

Commit: `feat(superadmin): bot-accounts page with CRUD + assign + delete`

### Task SP2-10: Bosses management

Backend: GET/POST/DELETE `/api/v1/superadmin/bosses`.
Frontend: `modules/superadmin/features/bosses/page.tsx`. Table of bosses with email, name, role, created_at, last_login_at; create form (email + name + role); delete with AlertDialog.
Source: `admin.py:bosses_view` + `templates/admin/bosses.html`.

Commit: `feat(superadmin): bosses CRUD`

### Task SP2-11: Prompts + note templates + agent triggers (3 related pages, 1 task)

Backend:
- `/api/v1/superadmin/prompts` GET (list) + POST (create) + GET/PATCH/DELETE `/:id`
- `/api/v1/superadmin/note-templates` CRUD
- `/api/v1/superadmin/agent-triggers` CRUD

Frontend: 3 sibling features.
- `prompts/list-page.tsx` (table) + `prompts/detail-page.tsx` (textarea editor with version note)
- `note-templates/page.tsx` (table + dialog)
- `agent-triggers/page.tsx` (table + create dialog with cron/event picker)

Source: `admin.py:prompts_*, note_templates_*, agent_triggers_*` + templates.

Commit: `feat(superadmin): prompts + note-templates + agent-triggers CRUD`

### Task SP2-12: Audit log + retrieval pipelines (2 pages, 1 task)

Backend:
- `/api/v1/superadmin/audit-log?cursor&limit` (paginated, read-only)
- `/api/v1/superadmin/retrieval-pipelines` GET/PATCH

Frontend:
- `audit-log/page.tsx`: virtual-scroll / paginated table with filters (actor, action, date range). Read-only.
- `retrieval-pipelines/page.tsx`: form with current RAG config (top_k, rerank model, threshold).

Source: `admin.py:audit_log_*, retrieval_pipelines_*`.

Commit: `feat(superadmin): audit-log + retrieval-pipelines pages`

---

## Phase F — Dashboard (1 task)

### Task SP2-13: Boss dashboard page

Backend: GET `/api/v1/admin/dashboard` returns `{recent_groups: [...5], today_items: [...10], stats_30d: {messages, tasks, reminders, decisions}, recent_activity: [...10]}`.

Frontend: replace stub `modules/admin/features/dashboard/page.tsx`. Layout: hero greeting → 4 stat cards row → 2-col (recent groups left, today action items right) → recent activity feed bottom. Reuse `<SummaryCard>` style from SP1 group detail.

Source: `app.py:dashboard_view` + `templates/dashboard.html`.

Commit: `feat(dashboard): boss home page`

---

## Phase G — Login port (1 task)

### Task SP2-14: React login page

**Files:**
- Create: `frontend/src/routes/login.tsx`
- Modify: `frontend/src/App.tsx` (add `/login` route outside RBAC)
- Backend: keep existing `POST /login` + `/api/oauth/google/start`. Add `GET /api/v1/auth/csrf` to bootstrap the cookie if absent (so the React login form can include CSRF in the first POST).

Layout: centered card (max-w-sm), brand mark + "Đăng nhập SMART_bot", email input, password input, "Đăng nhập" primary button, divider "hoặc", "Tiếp tục với Google" outline button (links to /api/oauth/google/start). Below: small "Liên hệ admin nếu chưa có tài khoản" muted text.

Submit: POST `/login` form-encoded with `_csrf` field. Backend returns 303 → React intercepts via `redirect` from the response → navigate to `/app`.

After this works, delete `src/web/templates/login.html` and remove the Jinja2 login route (keep POST /login handler — it's the actual login endpoint).

Commit: `feat(auth): React login page replacing Jinja2 template`

---

## Phase H — Cleanup (1 task)

### Task SP2-15: Delete legacy

**Only after all 13 boss pages + 11 super-admin pages render correctly in browser** (manual user verification).

- [ ] **Step 1: Delete legacy router**

```bash
git rm src/web/routes/app.py
git rm src/web/routes/admin.py
```

- [ ] **Step 2: Remove from app factory**

In `src/main.py` delete:
```python
app.include_router(web_app.router, prefix="/legacy-app")
app.include_router(web_admin.router)
```

Also remove the imports.

- [ ] **Step 3: Delete Jinja2 templates**

```bash
git rm src/web/templates/{dashboard,groups,group_detail,reminders,_reminders_list,projects,action_items,channels,usage,subscription,settings_account,settings_ai,settings_general,login,base}.html
git rm -r src/web/templates/admin/
```

Keep `spa-missing.html` (still used).

- [ ] **Step 4: Delete Jinja2 static**

```bash
git rm src/web/static/app.js src/web/static/style.css
```

- [ ] **Step 5: Delete or update legacy tests**

Grep for `/legacy-app` in `tests/`. Delete tests that asserted on Jinja2 rendering specifically; keep tests that hit the backend logic (those should be refactored to call the new JSON endpoints — but if they duplicate the new TDD tests, just delete).

- [ ] **Step 6: Full regression**

```bash
pytest tests/ -x -q 2>&1 | tail -5
cd frontend && pnpm build && pnpm tsc --noEmit && cd ..
```

- [ ] **Step 7: Commit**

```bash
git commit -m "chore(cleanup): remove legacy Jinja2 admin (app.py, admin.py, templates)"
```

---

## Phase I — Final smoke + Playwright (1 task)

### Task SP2-16: Update Playwright suite

Expand `frontend/tests/{smoke,rbac}.spec.ts` and add new files per feature:
- `tests/admin-flow.spec.ts`: login → dashboard → groups → create + delete → reminders → action items
- `tests/superadmin-flow.spec.ts`: bot-accounts CRUD, prompts CRUD, audit-log loads

Each test ~30 lines. Gated by env-var session cookies (same pattern as SP1).

Run `pnpm e2e` end-to-end. Document expected setup in `frontend/README.md` if not already.

Commit: `test(e2e): admin + superadmin flow suite`

---

## Coverage vs spec

| Spec section | Tasks |
|---|---|
| 2 Schema migrations | SP2-1 |
| 3 Boss API | SP2-3, 4, 5, 6, 7, 13 |
| 3 Super-admin API | SP2-8, 9, 10, 11, 12 |
| 4 Frontend pages (boss 13) | SP2-3 (settings ×3), 4 (groups list), SP1 group detail, 5 (reminders), 6 (projects + action-items), 7 (channels+usage+sub), 13 (dashboard) |
| 4 Frontend pages (superadmin 11) | SP2-8 (models+routes+budgets ×4), 9 (bot-accounts), 10 (bosses), 11 (prompts ×2 + note-templates + agent-triggers ×4), 12 (audit + retrieval ×2) |
| 5 Login port | SP2-14 |
| 6 Cleanup | SP2-15 |
| 7 Testing/DoD | SP2-16 + per-task tests |

Notes:
- Every task ends with a build + typecheck check before commit.
- If any page reveals an unforeseen backing data shape gap (table missing, column missing), the subagent should report DONE_WITH_CONCERNS rather than invent a schema. Schema additions go in their own follow-up migration commit.
- After SP2-15, the URL space is: `/app/*` (SPA only), `/api/*`, `/login`, `/api/oauth/*`, plus the existing `/test/*` web test channel. No more `/legacy-app/*`.
