# Web Frontend Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Vite+React+shadcn/ui frontend foundation served by FastAPI, with separate `admin` and `superadmin` modules gated by RBAC, plus two sample pages (Super-admin · Models & Bots, Admin · Group note viewer) to validate the design system.

**Architecture:** One SPA at `/app/*`. Two route namespaces (`/app/admin/*`, `/app/superadmin/*`), each as a self-contained module folder (routes + nav + layout + features). Shared `components/ui` (shadcn), `components/app-shell`, `lib/` infrastructure. FastAPI serves built static at `/app` with catch-all for SPA routing. RBAC enforced both at React route loader (`requireRole`) and FastAPI deps (`Depends(require_*)`).

**Tech Stack:** Vite 7 · React 19 · TypeScript · Tailwind CSS v4 · shadcn/ui · React Router v6 (data router) · TanStack Query v5 · TanStack Table v8 · lucide-react · pnpm. Backend: FastAPI (existing) · asyncpg · pytest. Tests: Playwright for E2E.

**Reference spec:** `docs/superpowers/specs/2026-06-03-web-design-system-design.md`

---

## Pre-flight

Backend already has `src/web/deps.py:require_superadmin`. We need to add a `require_boss` for `/api/v1/admin/*` and a clean `/api/v1/me` endpoint with `roles` list. Existing Jinja2 routes at `/admin/*` and `/app/*` (server-rendered) must keep working — we mount the new SPA under `/app` taking over that path, so confirm the old `/app` Jinja2 route in `src/web/routes/app.py` either is moved or coexists. **Strategy chosen:** rename the old Jinja2 `/app` namespace to `/legacy-app` for the lifetime of SP1 (so users of the new SPA don't collide). SP2 will delete `/legacy-app` once all pages port over.

---

## Phase 1 — Frontend scaffold

### Task 1: Initialize `frontend/` with Vite + React + TS + pnpm

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/pnpm-lock.yaml` (auto)
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`, `frontend/tsconfig.app.json`, `frontend/tsconfig.node.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`, `frontend/src/App.tsx`
- Modify: `.gitignore` (append `frontend/node_modules`, `frontend/dist`, `src/web/static/app/`)

- [ ] **Step 1: Run Vite scaffold**

Run from repo root:

```bash
cd frontend 2>/dev/null || mkdir frontend && cd frontend
pnpm create vite@latest . --template react-ts
# Answer: package name = frontend, do not overwrite if asked (we'll overwrite vite.config.ts later)
pnpm install
```

Expected: `frontend/package.json` exists, deps installed.

- [ ] **Step 2: Overwrite `frontend/vite.config.ts`**

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  base: '/app/',
  build: {
    outDir: '../src/web/static/app',
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: false },
      '/auth': { target: 'http://localhost:8000', changeOrigin: false },
    },
  },
});
```

- [ ] **Step 3: Update `.gitignore`**

Append at end:

```
# frontend
frontend/node_modules
frontend/dist
src/web/static/app/
```

- [ ] **Step 4: Verify build works**

```bash
cd frontend && pnpm build
ls ../src/web/static/app/
```

Expected: `index.html`, `assets/` directory present in `src/web/static/app/`.

- [ ] **Step 5: Commit**

```bash
git add frontend/ .gitignore
git commit -m "feat(frontend): scaffold Vite+React+TS in frontend/"
```

---

### Task 2: Add Tailwind v4 + shadcn/ui setup + design tokens

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/styles/globals.css`
- Modify: `frontend/src/main.tsx` (import globals)
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.js`
- Create: `frontend/components.json` (shadcn config)
- Modify: `frontend/tsconfig.json` + `frontend/tsconfig.app.json` (path alias)

- [ ] **Step 1: Install Tailwind v4 + shadcn deps**

```bash
cd frontend
pnpm add -D tailwindcss@^4 @tailwindcss/postcss postcss autoprefixer
pnpm add lucide-react class-variance-authority clsx tailwind-merge
pnpm add @radix-ui/react-slot
```

- [ ] **Step 2: Create `frontend/postcss.config.js`**

```js
export default {
  plugins: { '@tailwindcss/postcss': {} },
};
```

- [ ] **Step 3: Create `frontend/tailwind.config.ts`**

```ts
import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
        border: 'hsl(var(--border))',
        card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--foreground))' },
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
        destructive: { DEFAULT: 'hsl(var(--danger))', foreground: 'hsl(0 0% 100%)' },
        accent: { DEFAULT: 'hsl(var(--hover))', foreground: 'hsl(var(--foreground))' },
        ring: 'hsl(var(--primary))',
        ok: 'hsl(var(--ok))',
        warn: 'hsl(var(--warn))',
        info: 'hsl(var(--info))',
        dim: 'hsl(var(--dim))',
      },
      borderRadius: { lg: '10px', md: '8px', sm: '6px' },
      fontFamily: {
        sans: ['"Inter var"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
} satisfies Config;
```

- [ ] **Step 4: Create `frontend/src/styles/globals.css`**

```css
@import 'tailwindcss';

@font-face {
  font-family: 'Inter var';
  src: url('https://rsms.me/inter/font-files/InterVariable.woff2') format('woff2');
  font-weight: 100 900;
  font-display: swap;
}

:root {
  --background: 240 6% 7%;
  --bg-subtle: 240 6% 8.5%;
  --foreground: 0 0% 98%;
  --muted: 240 4% 12%;
  --muted-foreground: 240 5% 60%;
  --dim: 240 4% 38%;
  --border: 240 5% 14%;
  --border-strong: 240 5% 18%;
  --card: 240 5% 9%;
  --hover: 240 5% 11%;
  --primary: 168 65% 55%;
  --primary-soft: 168 50% 18%;
  --primary-foreground: 170 80% 6%;
  --danger: 0 60% 60%;
  --ok: 142 50% 55%;
  --warn: 38 88% 60%;
  --info: 210 80% 65%;
  --radius: 8px;
}

.light {
  --background: 0 0% 100%;
  --bg-subtle: 240 10% 98.5%;
  --foreground: 240 10% 4%;
  --muted: 240 5% 96%;
  --muted-foreground: 240 4% 42%;
  --dim: 240 4% 60%;
  --border: 240 6% 92%;
  --border-strong: 240 6% 86%;
  --card: 0 0% 100%;
  --hover: 240 5% 97%;
  --primary: 168 75% 32%;
  --primary-soft: 168 60% 94%;
  --primary-foreground: 0 0% 100%;
  --info: 210 80% 50%;
  --ok: 142 50% 40%;
  --warn: 38 88% 45%;
  --danger: 0 60% 50%;
}

* { box-sizing: border-box; }
html, body, #root { height: 100%; background: hsl(var(--background)); }
body {
  margin: 0;
  font-family: 'Inter var', 'Inter', system-ui, sans-serif;
  font-feature-settings: 'cv11', 'ss01', 'ss03';
  color: hsl(var(--foreground));
  font-size: 13.5px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
```

- [ ] **Step 5: Import globals in `frontend/src/main.tsx`**

Replace file content with:

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles/globals.css';
import App from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

- [ ] **Step 6: Update `frontend/tsconfig.app.json` path alias**

Open `frontend/tsconfig.app.json`, in `compilerOptions` add:

```json
"baseUrl": ".",
"paths": { "@/*": ["src/*"] }
```

- [ ] **Step 7: Create `frontend/components.json` (shadcn config)**

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/styles/globals.css",
    "baseColor": "zinc",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }
}
```

- [ ] **Step 8: Create `frontend/src/lib/utils.ts` (shadcn helper)**

```ts
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 9: Test placeholder render**

Replace `frontend/src/App.tsx` content:

```tsx
export default function App() {
  return (
    <div className="min-h-screen flex items-center justify-center text-foreground">
      <div className="text-center">
        <h1 className="text-2xl font-semibold tracking-tight">SMART_bot</h1>
        <p className="text-muted-foreground mt-2">Frontend foundation OK ✓</p>
        <button
          className="mt-4 px-3 py-2 rounded-md bg-primary text-primary-foreground text-sm"
          onClick={() => document.documentElement.classList.toggle('light')}
        >
          Toggle theme
        </button>
      </div>
    </div>
  );
}
```

Run: `cd frontend && pnpm dev`
Open `http://localhost:5173`. Expected: heading visible, button toggles between dark/light. Background switches accordingly. Stop dev server (Ctrl+C).

- [ ] **Step 10: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): tailwind v4 + shadcn config + design tokens (teal accent)"
```

---

### Task 3: Install core shadcn/ui primitives

**Files:**
- Create: `frontend/src/components/ui/{button,dialog,dropdown-menu,input,label,sheet,tabs,table,tooltip,skeleton,separator,badge,avatar,checkbox,switch,command,popover}.tsx` (auto-generated by shadcn CLI)

- [ ] **Step 1: Install shadcn CLI deps**

```bash
cd frontend
pnpm dlx shadcn@latest init -y
```

If prompted about overwriting `components.json` / `globals.css`, choose **No** (we already configured them).

- [ ] **Step 2: Add primitives batch**

```bash
pnpm dlx shadcn@latest add button dialog dropdown-menu input label sheet tabs table tooltip skeleton separator badge avatar checkbox switch command popover sonner
```

Expected: files created under `src/components/ui/`. No errors.

- [ ] **Step 3: Verify a component imports cleanly**

In `frontend/src/App.tsx`, replace content:

```tsx
import { Button } from '@/components/ui/button';

export default function App() {
  return (
    <div className="min-h-screen p-8 space-y-4">
      <h1 className="text-2xl font-semibold">shadcn check</h1>
      <Button>Default</Button>
      <Button variant="outline">Outline</Button>
      <Button variant="ghost">Ghost</Button>
    </div>
  );
}
```

Run `pnpm dev`, open browser. Expected: 3 buttons rendered, no console errors. Stop server.

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): install shadcn primitives (button, dialog, table, command, ...)"
```

---

## Phase 2 — FastAPI integration

### Task 4: Mount built SPA at `/app` with catch-all for client-side routing

**Files:**
- Modify: `src/web/routes/app.py` (rename old Jinja2 mount to `/legacy-app`)
- Modify: `src/web/__init__.py` or wherever routers register (locate via grep)
- Create: `src/web/routes/spa.py`

- [ ] **Step 1: Locate where `app.py` router is included**

```bash
grep -rn "from src.web.routes" src/ --include="*.py"
grep -rn "include_router" src/ --include="*.py" | grep -v test
```

Identify the file (likely `src/web/__init__.py` or `main.py`) where routers are wired.

- [ ] **Step 2: Move the Jinja2 `/app` namespace**

Edit `src/web/routes/app.py`. Find the `APIRouter(prefix="/app", ...)` declaration and change prefix to `/legacy-app`:

```python
router = APIRouter(prefix="/legacy-app", tags=["legacy-app"])
```

Run existing tests for the legacy app to confirm only URL paths changed (test files reference URLs — grep):

```bash
grep -rn '"/app/' tests/ src/web/ --include="*.py" --include="*.html"
```

For each match in tests, change `/app/` → `/legacy-app/`. For matches in templates (`<a href="/app/...">`), also update.

- [ ] **Step 3: Create `src/web/routes/spa.py`**

```python
"""Mount the Vite-built SPA at /app and serve index.html for any
sub-path so React Router can handle client-side routing."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

SPA_DIR = Path("src/web/static/app")
INDEX_HTML = SPA_DIR / "index.html"

router = APIRouter()


def mount_spa(app) -> None:
    """Mount /app/assets static files + catch-all route returning index.html.

    Called from the FastAPI app factory after all other routes are registered.
    """
    if SPA_DIR.exists():
        app.mount(
            "/app/assets",
            StaticFiles(directory=str(SPA_DIR / "assets")),
            name="spa-assets",
        )

    @app.get("/app", include_in_schema=False)
    @app.get("/app/{rest:path}", include_in_schema=False)
    async def spa_index(request: Request, rest: str = "") -> FileResponse:
        if not INDEX_HTML.exists():
            return FileResponse(
                "src/web/templates/spa-missing.html", status_code=503
            )
        return FileResponse(INDEX_HTML)
```

- [ ] **Step 4: Create placeholder for missing build**

```bash
cat > src/web/templates/spa-missing.html <<'EOF'
<!doctype html>
<html><body style="font-family:system-ui;padding:40px;max-width:600px">
<h1>SPA build chưa tồn tại</h1>
<p>Chạy <code>cd frontend && pnpm build</code> rồi reload trang.</p>
</body></html>
EOF
```

- [ ] **Step 5: Wire `mount_spa` in app factory**

Open the app factory (file found in Step 1) and add after all other routers are included:

```python
from src.web.routes.spa import mount_spa
mount_spa(app)
```

- [ ] **Step 6: Run existing test suite to confirm no regression**

```bash
pytest tests/ -x -q
```

Expected: all existing tests pass (legacy-app URL changes propagated correctly).

- [ ] **Step 7: Build frontend + smoke test via FastAPI**

```bash
cd frontend && pnpm build && cd ..
./scripts/restart.sh   # or however the user runs uvicorn
curl -s http://localhost:8000/app | head -5
curl -s http://localhost:8000/app/admin/anything | head -5
```

Expected: both return the same `index.html` (contains `<div id="root">`).

- [ ] **Step 8: Commit**

```bash
git add src/web/routes/app.py src/web/routes/spa.py src/web/templates/spa-missing.html src/web/__init__.py tests/ src/web/templates/
git commit -m "feat(web): mount Vite SPA at /app, move legacy Jinja2 to /legacy-app"
```

---

## Phase 3 — Backend API: /api/v1/me + RBAC

### Task 5: Add `require_boss` dep + `/api/v1/me` endpoint

**Files:**
- Modify: `src/web/deps.py`
- Create: `src/web/routes/api_me.py`
- Create: `tests/integration/test_api_me.py`
- Modify: app factory (include the new router)

- [ ] **Step 1: Add `require_boss` to `src/web/deps.py`**

Open `src/web/deps.py` and append:

```python
async def require_boss(
    ctx: BossContext = Depends(get_current_boss),
) -> BossContext:
    """Allow boss or superadmin (superadmin implies boss permissions)."""
    if ctx.user_role not in ("boss", "superadmin"):
        raise HTTPException(status_code=403, detail="boss only")
    return ctx
```

- [ ] **Step 2: Write the failing test**

Create `tests/integration/test_api_me.py`:

```python
"""Tests for GET /api/v1/me."""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_me_unauthenticated_returns_401(client: AsyncClient):
    r = await client.get("/api/v1/me")
    assert r.status_code == 401


async def test_me_returns_user_with_roles_for_boss(
    client: AsyncClient, logged_in_boss
):
    r = await client.get("/api/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == logged_in_boss.boss_id
    assert "boss" in body["roles"]
    assert "superadmin" not in body["roles"]


async def test_me_returns_both_roles_for_superadmin(
    client: AsyncClient, logged_in_superadmin
):
    r = await client.get("/api/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert set(body["roles"]) == {"boss", "superadmin"}
```

If `logged_in_boss` / `logged_in_superadmin` fixtures don't yet exist in `tests/conftest.py`, add them — they should create a user row in test DB and inject the session cookie into the AsyncClient. Reference the existing test login pattern (grep `tests/conftest.py` for "session_cookie" or similar).

- [ ] **Step 3: Run test, expect failure**

```bash
pytest tests/integration/test_api_me.py -v
```

Expected: 404 (route not registered yet).

- [ ] **Step 4: Implement `/api/v1/me`**

Create `src/web/routes/api_me.py`:

```python
"""Current user info endpoint for the SPA."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.repositories.base import BossContext
from src.web.deps import get_current_boss

router = APIRouter(prefix="/api/v1", tags=["me"])


@router.get("/me")
async def get_me(ctx: BossContext = Depends(get_current_boss)) -> dict:
    roles = ["boss"]
    if ctx.user_role == "superadmin":
        roles.append("superadmin")
    return {
        "id": ctx.boss_id,
        "roles": roles,
    }
```

- [ ] **Step 5: Wire router**

In the app factory, register:

```python
from src.web.routes import api_me
app.include_router(api_me.router)
```

- [ ] **Step 6: Run tests, expect pass**

```bash
pytest tests/integration/test_api_me.py -v
```

Expected: all 3 pass.

- [ ] **Step 7: Commit**

```bash
git add src/web/deps.py src/web/routes/api_me.py tests/integration/test_api_me.py src/web/__init__.py
git commit -m "feat(api): GET /api/v1/me + require_boss dep"
```

---

### Task 6: Backend — `/api/v1/superadmin/model-slots` + `/api/v1/superadmin/bot-accounts`

**Files:**
- Create: `src/web/routes/api_superadmin.py`
- Create: `tests/integration/test_api_superadmin.py`
- Modify: app factory

Inspect existing data sources first:
- Model slots: search for existing model-default config (`grep -rn "smart" src/ | grep -i "slot\|default"`).
- Bot accounts: see `src/channels/web/state_repo.py` for `bot_account` table created by migration `f349987`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for /api/v1/superadmin/* endpoints."""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_model_slots_requires_superadmin(
    client: AsyncClient, logged_in_boss
):
    r = await client.get("/api/v1/superadmin/model-slots")
    assert r.status_code == 403


async def test_model_slots_returns_three_slots(
    client: AsyncClient, logged_in_superadmin
):
    r = await client.get("/api/v1/superadmin/model-slots")
    assert r.status_code == 200
    slots = r.json()
    assert {s["slot"] for s in slots} == {"smart", "fast", "vision"}
    for s in slots:
        assert "model" in s
        assert "provider" in s
        assert s["status"] in ("active", "fallback", "missing")


async def test_bot_accounts_requires_superadmin(
    client: AsyncClient, logged_in_boss
):
    r = await client.get("/api/v1/superadmin/bot-accounts")
    assert r.status_code == 403


async def test_bot_accounts_returns_list_with_stats(
    client: AsyncClient, logged_in_superadmin, seed_bot_account
):
    r = await client.get("/api/v1/superadmin/bot-accounts?range=7d")
    assert r.status_code == 200
    accounts = r.json()
    assert len(accounts) >= 1
    acc = accounts[0]
    assert acc["id"]
    assert acc["channel"] in ("zalo", "telegram", "lark", "web")
    assert "messages_in" in acc
    assert "messages_out" in acc
    assert acc["status"] in ("online", "warn", "offline")
```

If `seed_bot_account` fixture doesn't exist, create it in `tests/conftest.py` to insert a row into the `bot_account` table.

- [ ] **Step 2: Run tests, expect 404 on the GET routes**

```bash
pytest tests/integration/test_api_superadmin.py -v
```

Expected: 404s.

- [ ] **Step 3: Implement endpoints**

Create `src/web/routes/api_superadmin.py`:

```python
"""Super-admin API endpoints for /api/v1/superadmin/*."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

import asyncpg
from fastapi import APIRouter, Depends

from src.config import settings
from src.repositories.base import BossContext
from src.web.deps import get_db, require_superadmin

router = APIRouter(prefix="/api/v1/superadmin", tags=["superadmin"])


@router.get("/model-slots")
async def list_model_slots(
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    smart = settings.model_smart
    fast = settings.model_fast
    vision = settings.model_vision

    def slot_status(name: str | None) -> Literal["active", "fallback", "missing"]:
        return "missing" if not name else "active"

    return [
        {
            "slot": "smart",
            "model": smart,
            "provider": _provider_of(smart),
            "status": slot_status(smart),
        },
        {
            "slot": "fast",
            "model": fast,
            "provider": _provider_of(fast),
            "status": slot_status(fast),
        },
        {
            "slot": "vision",
            "model": vision,
            "provider": _provider_of(vision),
            "status": "fallback" if not vision else "active",
        },
    ]


def _provider_of(model: str | None) -> str | None:
    if not model:
        return None
    if model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
        return "OpenAI"
    if "llama" in model or "mixtral" in model:
        return "Groq"
    if model.startswith("gemini"):
        return "Gemini"
    return "Unknown"


@router.get("/bot-accounts")
async def list_bot_accounts(
    range: str = "7d",
    db: asyncpg.Pool = Depends(get_db),
    _: BossContext = Depends(require_superadmin),
) -> list[dict]:
    days = int(range.rstrip("d")) if range.endswith("d") else 7
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT
              b.id, b.label, b.handle, b.channel, b.assigned_to, b.last_seen_at,
              COALESCE(SUM(CASE WHEN m.direction='in' THEN 1 ELSE 0 END), 0)::int  AS messages_in,
              COALESCE(SUM(CASE WHEN m.direction='out' THEN 1 ELSE 0 END), 0)::int AS messages_out
            FROM bot_account b
            LEFT JOIN bot_message m ON m.bot_account_id = b.id AND m.created_at >= $1
            GROUP BY b.id
            ORDER BY b.label
            """,
            since,
        )

    out: list[dict] = []
    for r in rows:
        last = r["last_seen_at"]
        if last is None:
            status = "offline"
        elif (datetime.now(timezone.utc) - last) > timedelta(minutes=10):
            status = "warn"
        else:
            status = "online"
        out.append(
            {
                "id": r["id"],
                "label": r["label"],
                "handle": r["handle"],
                "channel": r["channel"],
                "assigned_to": r["assigned_to"],
                "messages_in": r["messages_in"],
                "messages_out": r["messages_out"],
                "status": status,
            }
        )
    return out
```

If the `bot_message` table doesn't exist (verify via `\dt` or grep migrations), substitute with a hardcoded `messages_in = 0, messages_out = 0` for SP1 and mark a TODO in the spec's risks section. Run `grep -rn "CREATE TABLE bot_message" src/` first.

- [ ] **Step 4: Wire router**

In app factory:

```python
from src.web.routes import api_superadmin
app.include_router(api_superadmin.router)
```

- [ ] **Step 5: Run tests, expect pass**

```bash
pytest tests/integration/test_api_superadmin.py -v
```

Expected: all 4 pass.

- [ ] **Step 6: Commit**

```bash
git add src/web/routes/api_superadmin.py tests/integration/test_api_superadmin.py src/web/__init__.py
git commit -m "feat(api): /api/v1/superadmin/model-slots + /api/v1/superadmin/bot-accounts"
```

---

### Task 7: Backend — `/api/v1/admin/groups/:id` + sub-endpoints

**Files:**
- Create: `src/web/routes/api_admin.py`
- Create: `tests/integration/test_api_admin_groups.py`
- Modify: app factory

The shape of existing group/message data:
- `groups` table with `id`, `name`, `channel`, `owner_id`
- `messages` table (or wherever group messages live) — grep `grep -rn "groups\b" src/repositories/`
- Extracted items — likely `reminders`, `tasks`, `decisions` tables (check via `grep -rn "CREATE TABLE" src/`)

If the data shape doesn't match exactly, adapt the queries — keep the response contract from the spec.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for /api/v1/admin/groups/:id and sub-endpoints."""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_group_detail_unauthenticated(client: AsyncClient):
    r = await client.get("/api/v1/admin/groups/1")
    assert r.status_code == 401


async def test_group_detail_forbidden_for_non_owner(
    client: AsyncClient, logged_in_boss, seed_group_owned_by_other
):
    r = await client.get(f"/api/v1/admin/groups/{seed_group_owned_by_other.id}")
    assert r.status_code == 403


async def test_group_detail_returns_meta(
    client: AsyncClient, logged_in_boss, seed_group_owned_by_boss
):
    g = seed_group_owned_by_boss
    r = await client.get(f"/api/v1/admin/groups/{g.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == g.id
    assert body["name"] == g.name
    assert body["channel"] in ("zalo", "telegram", "lark", "web")
    assert "members_count" in body
    assert "messages_30d" in body
    assert "last_active_at" in body


async def test_group_timeline_returns_messages(
    client: AsyncClient, logged_in_boss, seed_group_with_messages
):
    g = seed_group_with_messages
    r = await client.get(f"/api/v1/admin/groups/{g.id}/timeline?limit=20")
    assert r.status_code == 200
    body = r.json()
    assert "messages" in body
    assert len(body["messages"]) >= 1
    m = body["messages"][0]
    assert {"id", "author_name", "author_kind", "text", "created_at"} <= set(m)


async def test_group_stats_returns_four_metrics(
    client: AsyncClient, logged_in_boss, seed_group_owned_by_boss
):
    r = await client.get(f"/api/v1/admin/groups/{seed_group_owned_by_boss.id}/stats?range=7d")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"messages", "tasks", "reminders", "decisions"}


async def test_group_members_returns_list(
    client: AsyncClient, logged_in_boss, seed_group_with_members
):
    r = await client.get(f"/api/v1/admin/groups/{seed_group_with_members.id}/members")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 1
    assert {"id", "name", "role"} <= set(body[0])
```

If the seed fixtures don't exist, add them in `tests/conftest.py` (small dataclasses + INSERT statements scoped to the test DB).

- [ ] **Step 2: Run tests, expect 404 / wrong status**

```bash
pytest tests/integration/test_api_admin_groups.py -v
```

- [ ] **Step 3: Implement endpoints**

Create `src/web/routes/api_admin.py`. The skeleton:

```python
"""Admin (boss) API endpoints for /api/v1/admin/*."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from src.repositories.base import BossContext
from src.web.deps import get_db, require_boss

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


async def _require_group_owner(
    group_id: int, ctx: BossContext, db: asyncpg.Pool
) -> asyncpg.Record:
    async with db.acquire() as c:
        row = await c.fetchrow(
            "SELECT id, name, channel, owner_id, last_active_at "
            "FROM groups WHERE id=$1",
            group_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="group not found")
    if row["owner_id"] != ctx.boss_id and ctx.user_role != "superadmin":
        raise HTTPException(status_code=403, detail="not your group")
    return row


@router.get("/groups/{group_id}")
async def get_group(
    group_id: int,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    row = await _require_group_owner(group_id, ctx, db)
    since30 = datetime.now(timezone.utc) - timedelta(days=30)
    async with db.acquire() as c:
        count_msg = await c.fetchval(
            "SELECT COUNT(*) FROM messages WHERE group_id=$1 AND created_at>=$2",
            group_id, since30,
        )
        count_mem = await c.fetchval(
            "SELECT COUNT(*) FROM group_members WHERE group_id=$1",
            group_id,
        )
    return {
        "id": row["id"],
        "name": row["name"],
        "channel": row["channel"],
        "members_count": int(count_mem),
        "messages_30d": int(count_msg),
        "last_active_at": row["last_active_at"].isoformat() if row["last_active_at"] else None,
    }


@router.get("/groups/{group_id}/timeline")
async def get_timeline(
    group_id: int,
    limit: int = 20,
    cursor: str | None = None,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    await _require_group_owner(group_id, ctx, db)
    args: list = [group_id]
    cursor_sql = ""
    if cursor:
        cursor_sql = " AND created_at < $2"
        args.append(datetime.fromisoformat(cursor))
    args.append(limit)
    async with db.acquire() as c:
        rows = await c.fetch(
            f"""
            SELECT id, author_name, author_kind, text, created_at
            FROM messages
            WHERE group_id=$1{cursor_sql}
            ORDER BY created_at DESC
            LIMIT ${len(args)}
            """,
            *args,
        )
    msgs = [
        {
            "id": r["id"],
            "author_name": r["author_name"],
            "author_kind": r["author_kind"],
            "text": r["text"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]
    return {
        "messages": msgs,
        "next_cursor": msgs[-1]["created_at"] if len(msgs) == limit else None,
    }


@router.get("/groups/{group_id}/stats")
async def get_stats(
    group_id: int,
    range: str = "7d",
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    await _require_group_owner(group_id, ctx, db)
    days = int(range.rstrip("d")) if range.endswith("d") else 7
    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with db.acquire() as c:
        msg = await c.fetchval(
            "SELECT COUNT(*) FROM messages WHERE group_id=$1 AND created_at>=$2",
            group_id, since,
        )
        task = await c.fetchval(
            "SELECT COUNT(*) FROM tasks WHERE group_id=$1 AND created_at>=$2",
            group_id, since,
        )
        rem = await c.fetchval(
            "SELECT COUNT(*) FROM reminders WHERE group_id=$1 AND created_at>=$2",
            group_id, since,
        )
        dec = await c.fetchval(
            "SELECT COUNT(*) FROM decisions WHERE group_id=$1 AND created_at>=$2",
            group_id, since,
        )
    return {
        "messages": int(msg),
        "tasks": int(task),
        "reminders": int(rem),
        "decisions": int(dec),
    }


@router.get("/groups/{group_id}/members")
async def get_members(
    group_id: int,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    await _require_group_owner(group_id, ctx, db)
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT id, display_name, role, last_seen_at
            FROM group_members
            WHERE group_id=$1
            ORDER BY display_name
            """,
            group_id,
        )
    return [
        {
            "id": r["id"],
            "name": r["display_name"],
            "role": r["role"],
            "last_seen_at": r["last_seen_at"].isoformat() if r["last_seen_at"] else None,
        }
        for r in rows
    ]


@router.get("/groups/{group_id}/summary")
async def get_summary(
    group_id: int,
    date: str = "today",
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    await _require_group_owner(group_id, ctx, db)
    # SP1: return the most recent cached AI summary; if no summary exists,
    # return null body. Generating-on-demand is out of scope here.
    async with db.acquire() as c:
        row = await c.fetchrow(
            """
            SELECT body, updated_at FROM group_summaries
            WHERE group_id=$1 AND date_label=$2
            ORDER BY updated_at DESC LIMIT 1
            """,
            group_id, date,
        )
    if not row:
        return {"body": None, "updated_at": None}
    return {"body": row["body"], "updated_at": row["updated_at"].isoformat()}


@router.get("/groups/{group_id}/items")
async def get_items(
    group_id: int,
    date: str = "today",
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    await _require_group_owner(group_id, ctx, db)
    # Combine tasks, reminders, decisions from today (or per `date`) into one
    # ordered list with a `type` discriminator.
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT id, 'task' AS type, text, assignee, due_at, created_at
              FROM tasks WHERE group_id=$1 AND DATE(created_at)=CURRENT_DATE
            UNION ALL
            SELECT id, 'reminder', text, NULL, fires_at, created_at
              FROM reminders WHERE group_id=$1 AND DATE(created_at)=CURRENT_DATE
            UNION ALL
            SELECT id, 'decision', text, decided_by, NULL, created_at
              FROM decisions WHERE group_id=$1 AND DATE(created_at)=CURRENT_DATE
            ORDER BY created_at
            """,
            group_id,
        )
    return [
        {
            "id": r["id"],
            "type": r["type"],
            "text": r["text"],
            "assignee": r["assignee"],
            "due_at": r["due_at"].isoformat() if r["due_at"] else None,
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


@router.get("/groups/{group_id}/files")
async def get_files(
    group_id: int,
    limit: int = 10,
    ctx: BossContext = Depends(require_boss),
    db: asyncpg.Pool = Depends(get_db),
) -> list[dict]:
    await _require_group_owner(group_id, ctx, db)
    async with db.acquire() as c:
        rows = await c.fetch(
            """
            SELECT id, kind, name, url, created_at
            FROM group_artifacts
            WHERE group_id=$1
            ORDER BY created_at DESC LIMIT $2
            """,
            group_id, limit,
        )
    return [
        {
            "id": r["id"],
            "kind": r["kind"],
            "name": r["name"],
            "url": r["url"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]
```

**Note:** if some referenced tables (`tasks`, `reminders`, `decisions`, `group_summaries`, `group_artifacts`, `group_members`) don't exist in current schema, return empty lists / `None` placeholders and add a note in the spec's "Open" section that a follow-up data-shape audit is required. Do NOT invent migrations in SP1.

- [ ] **Step 4: Wire router**

```python
from src.web.routes import api_admin
app.include_router(api_admin.router)
```

- [ ] **Step 5: Run tests, expect pass**

```bash
pytest tests/integration/test_api_admin_groups.py -v
```

Skip / xfail tests that depend on tables that don't yet exist, with a TODO referencing SP2 for the missing schema.

- [ ] **Step 6: Commit**

```bash
git add src/web/routes/api_admin.py tests/integration/test_api_admin_groups.py src/web/__init__.py
git commit -m "feat(api): /api/v1/admin/groups/* (detail, timeline, stats, members, summary, items, files)"
```

---

## Phase 4 — Frontend infrastructure (lib + AppShell)

### Task 8: lib/api.ts + lib/auth.ts + lib/theme.ts + lib/format.ts + lib/rbac.ts

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/auth.ts`
- Create: `frontend/src/lib/rbac.ts`
- Create: `frontend/src/lib/theme.ts`
- Create: `frontend/src/lib/format.ts`

- [ ] **Step 1: Install runtime deps**

```bash
cd frontend
pnpm add react-router-dom @tanstack/react-query @tanstack/react-table
```

- [ ] **Step 2: Create `frontend/src/lib/api.ts`**

```ts
function readCsrfCookie(): string | null {
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`API ${status}`);
  }
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const method = (init.method ?? 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') {
    const csrf = readCsrfCookie();
    if (csrf) headers.set('X-CSRF-Token', csrf);
  }

  const res = await fetch(path, { ...init, headers, credentials: 'include' });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
```

- [ ] **Step 3: Create `frontend/src/lib/auth.ts`**

```ts
import { queryOptions } from '@tanstack/react-query';
import { api } from './api';

export type Role = 'boss' | 'superadmin';
export type Me = { id: number; roles: Role[] };

export const meQuery = queryOptions({
  queryKey: ['me'] as const,
  queryFn: () => api<Me>('/api/v1/me'),
  staleTime: 60_000,
});
```

- [ ] **Step 4: Create `frontend/src/lib/rbac.ts`**

```ts
import { QueryClient } from '@tanstack/react-query';
import { LoaderFunction, redirect } from 'react-router-dom';
import { ApiError } from './api';
import { meQuery, Me, Role } from './auth';

export function defaultHomeFor(me: Me): string {
  return me.roles.includes('superadmin')
    ? '/app/superadmin/models'
    : '/app/admin/dashboard';
}

export function requireRole(role: Role, qc: QueryClient): LoaderFunction {
  return async () => {
    let me: Me;
    try {
      me = await qc.fetchQuery(meQuery);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        throw redirect('/login');
      }
      throw e;
    }
    if (!me.roles.includes(role)) {
      throw redirect(defaultHomeFor(me));
    }
    return me;
  };
}

export function requireAuth(qc: QueryClient): LoaderFunction {
  return async () => {
    try {
      const me = await qc.fetchQuery(meQuery);
      throw redirect(defaultHomeFor(me));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        throw redirect('/login');
      }
      throw e;
    }
  };
}
```

- [ ] **Step 5: Create `frontend/src/lib/theme.ts`**

```ts
const KEY = 'smart_theme';

export type Theme = 'dark' | 'light';

export function getTheme(): Theme {
  return (localStorage.getItem(KEY) as Theme) || 'dark';
}

export function applyTheme(t: Theme) {
  document.documentElement.classList.toggle('light', t === 'light');
  localStorage.setItem(KEY, t);
}

export function initTheme() {
  applyTheme(getTheme());
}

export function toggleTheme() {
  applyTheme(getTheme() === 'dark' ? 'light' : 'dark');
}
```

- [ ] **Step 6: Create `frontend/src/lib/format.ts`**

```ts
const RTF = new Intl.RelativeTimeFormat('vi', { numeric: 'auto' });

export function relativeTime(iso: string | null): string {
  if (!iso) return '—';
  const diffMs = new Date(iso).getTime() - Date.now();
  const minutes = Math.round(diffMs / 60_000);
  if (Math.abs(minutes) < 60) return RTF.format(minutes, 'minute');
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return RTF.format(hours, 'hour');
  const days = Math.round(hours / 24);
  return RTF.format(days, 'day');
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat('vi-VN').format(n);
}
```

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): lib (api, auth, rbac, theme, format)"
```

---

### Task 9: Shared components — ThemeToggle, StatusDot, EmptyState

**Files:**
- Create: `frontend/src/components/theme-toggle.tsx`
- Create: `frontend/src/components/status-dot.tsx`
- Create: `frontend/src/components/empty-state.tsx`

- [ ] **Step 1: Create `frontend/src/components/theme-toggle.tsx`**

```tsx
import { Lightbulb, LightbulbOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toggleTheme } from '@/lib/theme';
import { useState } from 'react';

export function ThemeToggle() {
  const [tick, setTick] = useState(0);
  const isLight = document.documentElement.classList.contains('light');
  return (
    <Button
      variant="outline"
      size="icon"
      aria-label="Đổi theme"
      onClick={() => {
        toggleTheme();
        setTick(t => t + 1);
      }}
      className="h-[30px] w-[30px]"
    >
      {isLight ? (
        <Lightbulb className="h-4 w-4 text-amber-500" />
      ) : (
        <LightbulbOff className="h-4 w-4" />
      )}
      <span className="sr-only">{tick}</span>
    </Button>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/status-dot.tsx`**

```tsx
import { cn } from '@/lib/utils';

type Status = 'ok' | 'warn' | 'err' | 'idle';

const COLORS: Record<Status, string> = {
  ok: 'bg-[hsl(var(--ok))] ring-[hsl(var(--ok)/0.12)]',
  warn: 'bg-[hsl(var(--warn))] ring-[hsl(var(--warn)/0.12)]',
  err: 'bg-[hsl(var(--danger))] ring-[hsl(var(--danger)/0.12)]',
  idle: 'bg-[hsl(var(--dim))] ring-transparent',
};

const TEXT: Record<Status, string> = {
  ok: 'text-[hsl(var(--ok))]',
  warn: 'text-[hsl(var(--warn))]',
  err: 'text-[hsl(var(--danger))]',
  idle: 'text-muted-foreground',
};

export function StatusDot({
  status,
  label,
  className,
}: {
  status: Status;
  label?: string;
  className?: string;
}) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-xs', TEXT[status], className)}>
      <span className={cn('h-1.5 w-1.5 rounded-full ring-[3px]', COLORS[status])} />
      {label}
    </span>
  );
}
```

- [ ] **Step 3: Create `frontend/src/components/empty-state.tsx`**

```tsx
import { LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6">
      <Icon className="h-10 w-10 text-[hsl(var(--dim))] mb-3" strokeWidth={1.5} />
      <h3 className="text-base font-medium tracking-tight">{title}</h3>
      {description && (
        <p className="text-sm text-muted-foreground mt-1 max-w-sm">{description}</p>
      )}
      {action && (
        <Button onClick={action.onClick} className="mt-5">
          {action.label}
        </Button>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/
git commit -m "feat(frontend): ThemeToggle + StatusDot + EmptyState components"
```

---

### Task 10: AppShell — sidebar collapsible + topbar + user dropdown + mobile drawer

**Files:**
- Create: `frontend/src/components/app-shell.tsx`
- Create: `frontend/src/components/user-menu.tsx`

This is the largest shared component. Read v3 mockup in `.superpowers/brainstorm/.../superadmin-config-v3.html` for visual reference.

- [ ] **Step 1: Create `frontend/src/components/user-menu.tsx`**

```tsx
import { ChevronDown, LogOut, Settings, User } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Me } from '@/lib/auth';

export function UserMenu({ me, collapsed }: { me: Me; collapsed: boolean }) {
  const initials = (String(me.id)[0] || 'U').toUpperCase();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex items-center gap-2.5 w-full px-3 py-2.5 border-t border-border hover:bg-[hsl(var(--hover))] transition-colors">
          <div className="h-7 w-7 rounded-full bg-gradient-to-br from-[hsl(168_70%_45%)] to-[hsl(200_65%_45%)] text-white text-[11px] font-semibold grid place-items-center shrink-0">
            {initials}
          </div>
          {!collapsed && (
            <>
              <div className="flex-1 text-left min-w-0">
                <div className="text-[12.5px] font-medium truncate">User #{me.id}</div>
                <div className="text-[11px] text-[hsl(var(--dim))]">
                  {me.roles.includes('superadmin') ? 'Super-admin' : 'Workspace owner'}
                </div>
              </div>
              <ChevronDown className="h-3.5 w-3.5 text-[hsl(var(--dim))]" />
            </>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" className="w-56">
        <DropdownMenuItem><User className="mr-2 h-4 w-4" />Hồ sơ</DropdownMenuItem>
        <DropdownMenuItem><Settings className="mr-2 h-4 w-4" />Cài đặt</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="text-destructive focus:text-destructive"
          onClick={() => { window.location.href = '/auth/logout'; }}
        >
          <LogOut className="mr-2 h-4 w-4" />Đăng xuất
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/app-shell.tsx`**

```tsx
import { ReactNode, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronLeft, Menu, Search, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from './theme-toggle';
import { UserMenu } from './user-menu';
import { Me } from '@/lib/auth';
import { cn } from '@/lib/utils';

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
};

export type NavSection = { label: string; items: NavItem[] };

export function AppShell({
  nav,
  me,
  breadcrumb,
  children,
}: {
  nav: NavSection[];
  me: Me;
  breadcrumb: ReactNode;
  children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const sb = collapsed ? '60px' : '232px';

  return (
    <div
      className="relative grid min-h-screen transition-[grid-template-columns] duration-200 md:grid-cols-[var(--sb)_1fr]"
      style={{ ['--sb' as string]: sb }}
    >
      {mobileOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/60 backdrop-blur-sm z-20"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={cn(
          'flex flex-col border-r border-border bg-card relative z-30',
          'md:static md:translate-x-0',
          'fixed inset-y-0 left-0 w-[260px] transition-transform',
          mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        )}
      >
        <div className={cn(
          'flex items-center justify-between gap-2 px-3.5 pt-3.5 pb-1',
          collapsed && 'justify-center px-1.5'
        )}>
          <div className={cn('flex items-center gap-2.5 overflow-hidden', collapsed && 'justify-center')}>
            <div className="h-[26px] w-[26px] rounded-[7px] bg-gradient-to-br from-[hsl(168_72%_48%)] to-[hsl(190_75%_40%)] text-white font-semibold text-xs grid place-items-center shrink-0 shadow-[0_0_0_1px_hsl(168_50%_28%),inset_0_1px_0_hsl(168_80%_70%/0.3)]">
              S
            </div>
            {!collapsed && <span className="text-sm font-semibold tracking-tight">SMART_bot</span>}
          </div>
          {!collapsed && (
            <button
              onClick={() => setCollapsed(true)}
              aria-label="Thu gọn"
              className="h-[26px] w-[26px] rounded-md grid place-items-center text-[hsl(var(--dim))] hover:text-foreground hover:bg-[hsl(var(--hover))]"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        <nav className="flex-1 overflow-y-auto px-2.5 py-2">
          {nav.map(section => (
            <div key={section.label}>
              {!collapsed && (
                <div className="text-[10px] uppercase tracking-wider text-[hsl(var(--dim))] px-2.5 pt-4 pb-1.5 font-medium">
                  {section.label}
                </div>
              )}
              {section.items.map(item => {
                const active = location.pathname.startsWith(item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    to={item.href}
                    onClick={() => setMobileOpen(false)}
                    className={cn(
                      'flex items-center gap-2.5 rounded-md px-2.5 py-[6.5px] text-[13px] text-muted-foreground transition-colors',
                      active && 'bg-[hsl(var(--hover))] text-foreground font-medium',
                      'hover:bg-[hsl(var(--hover))] hover:text-foreground',
                      collapsed && 'justify-center px-2.5'
                    )}
                  >
                    <Icon className={cn('h-[15px] w-[15px] shrink-0', active && 'text-primary')} strokeWidth={1.8} />
                    {!collapsed && <span className="truncate">{item.label}</span>}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        {collapsed && (
          <button
            onClick={() => setCollapsed(false)}
            aria-label="Mở rộng"
            className="absolute -right-3 top-4 h-6 w-6 rounded-full bg-card border border-border-strong grid place-items-center text-[hsl(var(--dim))] hover:text-foreground"
          >
            <ChevronLeft className="h-3 w-3 rotate-180" />
          </button>
        )}

        <UserMenu me={me} collapsed={collapsed} />
      </aside>

      <main>
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-border bg-[hsl(var(--background)/0.7)] backdrop-blur px-7 py-3.5 max-md:px-4">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => setMobileOpen(true)}
              className="md:hidden h-[30px] w-[30px] rounded-md border border-border grid place-items-center"
              aria-label="Mở menu"
            >
              <Menu className="h-4 w-4" />
            </button>
            <div className="text-[13px] text-muted-foreground truncate">{breadcrumb}</div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="h-[30px] gap-2 text-xs">
              <Search className="h-3.5 w-3.5" />
              <span className="max-sm:hidden">Tìm kiếm</span>
              <kbd className="bg-muted text-[hsl(var(--dim))] rounded px-1.5 py-0.5 text-[10px] font-mono">⌘K</kbd>
            </Button>
            <ThemeToggle />
          </div>
        </div>

        {children}
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Smoke-render in App.tsx**

Replace `frontend/src/App.tsx`:

```tsx
import { AppShell, NavSection } from './components/app-shell';
import { LayoutDashboard, Users } from 'lucide-react';

const nav: NavSection[] = [
  {
    label: 'Workspace',
    items: [
      { label: 'Dashboard', href: '/app/admin/dashboard', icon: LayoutDashboard },
      { label: 'Groups', href: '/app/admin/groups', icon: Users },
    ],
  },
];

export default function App() {
  return (
    <AppShell nav={nav} me={{ id: 1, roles: ['boss'] }} breadcrumb={<><span>Groups</span> <span className="text-[hsl(var(--dim))]">/</span> <b className="text-foreground font-medium">Phòng Kinh Doanh</b></>}>
      <div className="p-10">
        <h1 className="text-2xl font-semibold tracking-tight">Smoke test</h1>
        <p className="text-muted-foreground mt-1">AppShell renders</p>
      </div>
    </AppShell>
  );
}
```

Run `pnpm dev`, open `/app/` (via `pnpm dev` direct: `http://localhost:5173/app/`). Expected: sidebar with nav items, topbar with breadcrumb + search + theme toggle. Click collapse button → sidebar shrinks. Resize to <900px → hamburger button appears, sidebar becomes drawer. Theme toggle switches dark/light.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/app-shell.tsx frontend/src/components/user-menu.tsx frontend/src/App.tsx
git commit -m "feat(frontend): AppShell + UserMenu with collapse, mobile drawer, theme toggle"
```

---

### Task 11: DataTable + UserPicker

**Files:**
- Create: `frontend/src/components/data-table.tsx`
- Create: `frontend/src/components/user-picker.tsx`

- [ ] **Step 1: Create `frontend/src/components/data-table.tsx`**

```tsx
import { ReactNode } from 'react';
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { cn } from '@/lib/utils';

export type DataTableProps<T> = {
  columns: ColumnDef<T, any>[];
  data: T[];
  mobileLabel?: (col: ColumnDef<T, any>) => string;
  empty?: ReactNode;
};

export function DataTable<T>({ columns, data, mobileLabel, empty }: DataTableProps<T>) {
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });

  if (data.length === 0 && empty) return <>{empty}</>;

  return (
    <div className="rounded-[10px] bg-card shadow-[var(--shadow-card,0_0_0_1px_hsl(var(--border-strong)),0_1px_2px_rgba(0,0,0,.04))] overflow-hidden">
      <table className="w-full text-[13px]">
        <thead className="bg-[hsl(var(--bg-subtle))]">
          {table.getHeaderGroups().map(hg => (
            <tr key={hg.id}>
              {hg.headers.map(h => (
                <th
                  key={h.id}
                  className="text-left font-medium text-muted-foreground px-4 py-2.5 text-[11.5px] uppercase tracking-wide border-b border-border max-md:hidden"
                >
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map(row => (
            <tr
              key={row.id}
              className={cn(
                'transition-colors hover:bg-[hsl(var(--hover))]',
                'max-md:block max-md:p-3.5 max-md:border-b max-md:border-border'
              )}
            >
              {row.getVisibleCells().map(cell => (
                <td
                  key={cell.id}
                  data-label={mobileLabel ? mobileLabel(cell.column.columnDef) : ''}
                  className={cn(
                    'px-4 py-3 border-b border-border align-middle',
                    'max-md:block max-md:px-0 max-md:py-1 max-md:border-0',
                    'max-md:flex max-md:justify-between max-md:items-center max-md:gap-3',
                    'max-md:before:content-[attr(data-label)] max-md:before:text-[hsl(var(--dim))] max-md:before:text-[11px] max-md:before:uppercase max-md:before:tracking-wide'
                  )}
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/user-picker.tsx`**

```tsx
import { useState } from 'react';
import { Check, ChevronsUpDown, Search } from 'lucide-react';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export type UserPickerOption = { id: string | number; label: string; sub?: string };

export function UserPicker({
  options,
  value,
  onChange,
  placeholder = 'Chọn người…',
}: {
  options: UserPickerOption[];
  value?: UserPickerOption['id'];
  onChange: (id: UserPickerOption['id']) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const selected = options.find(o => o.id === value);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" role="combobox" className="w-full justify-between font-normal">
          {selected ? selected.label : <span className="text-muted-foreground">{placeholder}</span>}
          <ChevronsUpDown className="ml-2 h-3.5 w-3.5 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command>
          <CommandInput placeholder="Tìm theo tên..." />
          <CommandList>
            <CommandEmpty>Không tìm thấy.</CommandEmpty>
            <CommandGroup>
              {options.map(o => (
                <CommandItem
                  key={o.id}
                  onSelect={() => { onChange(o.id); setOpen(false); }}
                  className="flex items-center justify-between"
                >
                  <div>
                    <div>{o.label}</div>
                    {o.sub && <div className="text-xs text-muted-foreground">{o.sub}</div>}
                  </div>
                  <Check className={cn('h-4 w-4', value === o.id ? 'opacity-100' : 'opacity-0')} />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/
git commit -m "feat(frontend): DataTable + UserPicker components"
```

---

## Phase 5 — Module scaffolding + router

### Task 12: modules/admin and modules/superadmin scaffolds

**Files:**
- Create: `frontend/src/modules/admin/nav.ts`
- Create: `frontend/src/modules/admin/layout.tsx`
- Create: `frontend/src/modules/admin/routes.tsx`
- Create: `frontend/src/modules/superadmin/nav.ts`
- Create: `frontend/src/modules/superadmin/layout.tsx`
- Create: `frontend/src/modules/superadmin/routes.tsx`

- [ ] **Step 1: Create `frontend/src/modules/admin/nav.ts`**

```ts
import { LayoutDashboard, Users, Bell, FolderKanban, Link as LinkIcon, Settings } from 'lucide-react';
import type { NavSection } from '@/components/app-shell';

export const adminNav: NavSection[] = [
  {
    label: 'Workspace',
    items: [
      { label: 'Dashboard', href: '/app/admin/dashboard', icon: LayoutDashboard },
      { label: 'Groups', href: '/app/admin/groups', icon: Users },
      { label: 'Reminders', href: '/app/admin/reminders', icon: Bell },
      { label: 'Projects', href: '/app/admin/projects', icon: FolderKanban },
    ],
  },
  {
    label: 'Cài đặt',
    items: [
      { label: 'Channels', href: '/app/admin/channels', icon: LinkIcon },
      { label: 'Settings', href: '/app/admin/settings', icon: Settings },
    ],
  },
];
```

- [ ] **Step 2: Create `frontend/src/modules/admin/layout.tsx`**

```tsx
import { Outlet, useLoaderData, useMatches } from 'react-router-dom';
import { AppShell } from '@/components/app-shell';
import { Me } from '@/lib/auth';
import { adminNav } from './nav';

export default function AdminLayout() {
  const me = useLoaderData() as Me;
  const matches = useMatches();
  const crumbs = matches
    .filter(m => m.handle && (m.handle as any).breadcrumb)
    .map(m => (m.handle as any).breadcrumb);
  return (
    <AppShell
      nav={adminNav}
      me={me}
      breadcrumb={
        crumbs.length > 0 ? (
          crumbs.map((c, i) => (
            <span key={i}>
              {i > 0 && <span className="mx-2 text-[hsl(var(--dim))]">/</span>}
              {i === crumbs.length - 1 ? <b className="text-foreground font-medium">{c}</b> : c}
            </span>
          ))
        ) : (
          'Admin'
        )
      }
    >
      <Outlet />
    </AppShell>
  );
}
```

- [ ] **Step 3: Create `frontend/src/modules/admin/routes.tsx`**

```tsx
import { QueryClient } from '@tanstack/react-query';
import { RouteObject } from 'react-router-dom';
import { requireRole } from '@/lib/rbac';
import AdminLayout from './layout';
import GroupDetail, { groupDetailLoader } from './features/groups/group-detail';

export function adminRoutes(qc: QueryClient): RouteObject {
  return {
    path: '/app/admin',
    element: <AdminLayout />,
    loader: requireRole('boss', qc),
    id: 'admin',
    handle: { breadcrumb: 'Admin' },
    children: [
      { index: true, lazy: async () => ({ Component: (await import('./features/dashboard/page')).default }) },
      { path: 'dashboard', lazy: async () => ({ Component: (await import('./features/dashboard/page')).default }), handle: { breadcrumb: 'Dashboard' } },
      { path: 'groups', lazy: async () => ({ Component: (await import('./features/groups/list-page')).default }), handle: { breadcrumb: 'Groups' } },
      {
        path: 'groups/:groupId',
        element: <GroupDetail />,
        loader: groupDetailLoader(qc),
        handle: { breadcrumb: 'Group' },
      },
    ],
  };
}
```

Stub the lazy-loaded pages so the route table compiles. Create:

`frontend/src/modules/admin/features/dashboard/page.tsx`:

```tsx
export default function DashboardPage() {
  return <div className="p-10"><h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1><p className="text-muted-foreground mt-1">(SP2 sẽ build)</p></div>;
}
```

`frontend/src/modules/admin/features/groups/list-page.tsx`:

```tsx
export default function GroupsListPage() {
  return <div className="p-10"><h1 className="text-2xl font-semibold tracking-tight">Groups</h1><p className="text-muted-foreground mt-1">(SP2 sẽ build)</p></div>;
}
```

`frontend/src/modules/admin/features/groups/group-detail.tsx` (skeleton — real impl in Task 16):

```tsx
import { LoaderFunction, useParams } from 'react-router-dom';
import { QueryClient } from '@tanstack/react-query';

export const groupDetailLoader = (_qc: QueryClient): LoaderFunction => async ({ params }) => {
  return { groupId: params.groupId };
};

export default function GroupDetail() {
  const params = useParams();
  return <div className="p-10"><h1 className="text-2xl font-semibold tracking-tight">Group {params.groupId}</h1></div>;
}
```

- [ ] **Step 4: Create the same trio for `superadmin/`**

`frontend/src/modules/superadmin/nav.ts`:

```ts
import { Cpu, UserCog, FileText, BarChart3 } from 'lucide-react';
import type { NavSection } from '@/components/app-shell';

export const superadminNav: NavSection[] = [
  {
    label: 'Super-admin',
    items: [
      { label: 'Models & Bots', href: '/app/superadmin/models', icon: Cpu },
      { label: 'Users', href: '/app/superadmin/users', icon: UserCog },
      { label: 'Audit log', href: '/app/superadmin/audit', icon: FileText },
      { label: 'Usage', href: '/app/superadmin/usage', icon: BarChart3 },
    ],
  },
];
```

`frontend/src/modules/superadmin/layout.tsx`:

```tsx
import { Outlet, useLoaderData, useMatches } from 'react-router-dom';
import { AppShell } from '@/components/app-shell';
import { Me } from '@/lib/auth';
import { superadminNav } from './nav';

export default function SuperadminLayout() {
  const me = useLoaderData() as Me;
  const matches = useMatches();
  const crumbs = matches
    .filter(m => m.handle && (m.handle as any).breadcrumb)
    .map(m => (m.handle as any).breadcrumb);
  return (
    <AppShell
      nav={superadminNav}
      me={me}
      breadcrumb={
        crumbs.length > 0 ? (
          crumbs.map((c, i) => (
            <span key={i}>
              {i > 0 && <span className="mx-2 text-[hsl(var(--dim))]">/</span>}
              {i === crumbs.length - 1 ? <b className="text-foreground font-medium">{c}</b> : c}
            </span>
          ))
        ) : (
          'Super-admin'
        )
      }
    >
      <Outlet />
    </AppShell>
  );
}
```

`frontend/src/modules/superadmin/routes.tsx`:

```tsx
import { QueryClient } from '@tanstack/react-query';
import { RouteObject } from 'react-router-dom';
import { requireRole } from '@/lib/rbac';
import SuperadminLayout from './layout';

export function superadminRoutes(qc: QueryClient): RouteObject {
  return {
    path: '/app/superadmin',
    element: <SuperadminLayout />,
    loader: requireRole('superadmin', qc),
    id: 'superadmin',
    handle: { breadcrumb: 'Super-admin' },
    children: [
      { index: true, lazy: async () => ({ Component: (await import('./features/models/page')).default }) },
      { path: 'models', lazy: async () => ({ Component: (await import('./features/models/page')).default }), handle: { breadcrumb: 'Models & Bots' } },
    ],
  };
}
```

`frontend/src/modules/superadmin/features/models/page.tsx` (skeleton — real impl in Task 14):

```tsx
export default function ModelsPage() {
  return <div className="p-10"><h1 className="text-2xl font-semibold tracking-tight">Models & Bots</h1></div>;
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/
git commit -m "feat(frontend): modules/admin + modules/superadmin scaffolds with RBAC loaders"
```

---

### Task 13: App.tsx — wire QueryClient + Router + root redirect

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx` (init theme on boot)

- [ ] **Step 1: Replace `frontend/src/App.tsx`**

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { adminRoutes } from './modules/admin/routes';
import { superadminRoutes } from './modules/superadmin/routes';
import { requireAuth } from './lib/rbac';
import { Toaster } from '@/components/ui/sonner';

const qc = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
});

const router = createBrowserRouter([
  { path: '/app', loader: requireAuth(qc), id: 'root' },
  adminRoutes(qc),
  superadminRoutes(qc),
], { basename: '/' });

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>
  );
}
```

- [ ] **Step 2: Init theme in `frontend/src/main.tsx`**

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles/globals.css';
import App from './App';
import { initTheme } from './lib/theme';

initTheme();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

- [ ] **Step 3: Smoke test routing**

Build + run backend, then:

```bash
cd frontend && pnpm build && cd ..
./scripts/restart.sh  # or restart uvicorn
```

In browser:
- `http://localhost:8000/app` (logged out) → redirects to `/login` (handled by Jinja2 cũ).
- Login as boss → `/app` redirects to `/app/admin/dashboard`.
- Login as superadmin → `/app` redirects to `/app/superadmin/models`.
- Boss tries `/app/superadmin/models` → redirected to `/app/admin/dashboard`.

If any of these don't work, fix `defaultHomeFor` or `requireRole` in `lib/rbac.ts`.

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): App wires QueryClient + Router + root redirect by role"
```

---

## Phase 6 — Sample pages (real data)

### Task 14: Superadmin Models & Bots page — full implementation

**Files:**
- Create: `frontend/src/modules/superadmin/features/models/page.tsx` (replace skeleton)
- Create: `frontend/src/modules/superadmin/features/models/slot-card.tsx`
- Create: `frontend/src/modules/superadmin/features/models/bot-accounts-table.tsx`
- Create: `frontend/src/modules/superadmin/features/models/api.ts`

- [ ] **Step 1: API layer**

Create `frontend/src/modules/superadmin/features/models/api.ts`:

```ts
import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Slot = {
  slot: 'smart' | 'fast' | 'vision';
  model: string | null;
  provider: string | null;
  status: 'active' | 'fallback' | 'missing';
};

export type BotAccount = {
  id: number;
  label: string;
  handle: string;
  channel: string;
  assigned_to: string | null;
  messages_in: number;
  messages_out: number;
  status: 'online' | 'warn' | 'offline';
};

export const slotsQuery = queryOptions({
  queryKey: ['superadmin', 'model-slots'] as const,
  queryFn: () => api<Slot[]>('/api/v1/superadmin/model-slots'),
});

export const botAccountsQuery = queryOptions({
  queryKey: ['superadmin', 'bot-accounts', '7d'] as const,
  queryFn: () => api<BotAccount[]>('/api/v1/superadmin/bot-accounts?range=7d'),
});
```

- [ ] **Step 2: SlotCard component**

Create `frontend/src/modules/superadmin/features/models/slot-card.tsx`:

```tsx
import { type LucideIcon } from 'lucide-react';
import { StatusDot } from '@/components/status-dot';
import type { Slot } from './api';

const ICON_BY_SLOT: Record<Slot['slot'], string> = {
  smart: '⟳', fast: '⚡', vision: '◉',
};

export function SlotCard({ slot, icon: Icon }: { slot: Slot; icon: LucideIcon }) {
  const status =
    slot.status === 'active' ? 'ok' :
    slot.status === 'fallback' ? 'warn' : 'warn';
  const statusLabel =
    slot.status === 'active' ? 'Hoạt động' :
    slot.status === 'fallback' ? 'Fallback' : 'Thiếu cấu hình';

  return (
    <div className="rounded-[10px] bg-card p-4 shadow-[0_0_0_1px_hsl(var(--border-strong)),0_1px_2px_rgba(0,0,0,.04)] transition-transform hover:-translate-y-[1px]">
      <div className="h-[30px] w-[30px] rounded-[7px] bg-muted grid place-items-center text-primary mb-3.5">
        <Icon className="h-[15px] w-[15px]" strokeWidth={1.8} />
      </div>
      <div className="text-[10.5px] uppercase tracking-wider text-[hsl(var(--dim))] font-medium mb-1 capitalize">{slot.slot}</div>
      <div className={`text-[15px] font-medium tracking-tight ${!slot.model ? 'text-muted-foreground' : ''}`}>
        {slot.model ?? 'Chưa cấu hình'}
      </div>
      <div className="text-xs text-muted-foreground mt-0.5 mb-4">
        {slot.provider ?? 'Fallback → Smart slot'}
      </div>
      <div className="flex items-center justify-between pt-3.5 border-t border-border text-xs">
        <StatusDot status={status as any} label={statusLabel} />
        <a className="text-primary font-medium hover:underline underline-offset-[3px] cursor-pointer">
          {slot.status === 'missing' ? 'Thiết lập' : 'Đổi'}
        </a>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: BotAccountsTable**

Create `frontend/src/modules/superadmin/features/models/bot-accounts-table.tsx`:

```tsx
import { ColumnDef } from '@tanstack/react-table';
import { MoreHorizontal } from 'lucide-react';
import { DataTable } from '@/components/data-table';
import { StatusDot } from '@/components/status-dot';
import { Button } from '@/components/ui/button';
import { formatNumber } from '@/lib/format';
import type { BotAccount } from './api';

const STATUS_LABEL: Record<BotAccount['status'], { s: 'ok' | 'warn' | 'err'; label: string }> = {
  online: { s: 'ok', label: 'Online' },
  warn: { s: 'warn', label: 'Cần re-auth' },
  offline: { s: 'err', label: 'Mất kết nối' },
};

const CHANNEL_LABEL: Record<string, string> = {
  zalo: 'Zalo cá nhân',
  telegram: 'Telegram',
  lark: 'Lark',
  web: 'Web',
};

const columns: ColumnDef<BotAccount>[] = [
  {
    header: 'Account',
    accessorKey: 'label',
    cell: ({ row }) => (
      <div>
        <div className="font-medium tracking-tight">{row.original.label}</div>
        <div className="text-[hsl(var(--dim))] text-xs font-mono mt-0.5">{row.original.handle}</div>
      </div>
    ),
  },
  {
    header: 'Kênh',
    accessorKey: 'channel',
    cell: ({ row }) => (
      <span className="inline-flex items-center gap-1.5 px-[7px] py-[1px] rounded text-[11.5px] text-muted-foreground bg-muted font-medium">
        {CHANNEL_LABEL[row.original.channel] ?? row.original.channel}
      </span>
    ),
  },
  {
    header: 'Phân bổ',
    accessorKey: 'assigned_to',
    cell: ({ getValue }) => (
      <span className={getValue() ? '' : 'text-[hsl(var(--dim))]'}>{(getValue() as string) ?? 'Chưa gán'}</span>
    ),
  },
  {
    header: 'Tin nhắn 7d',
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground">
        <b className="font-medium text-foreground">{formatNumber(row.original.messages_in)}</b> in ·{' '}
        <b className="font-medium text-foreground">{formatNumber(row.original.messages_out)}</b> out
      </span>
    ),
  },
  {
    header: 'Trạng thái',
    cell: ({ row }) => {
      const m = STATUS_LABEL[row.original.status];
      return <StatusDot status={m.s} label={m.label} />;
    },
  },
  {
    id: 'actions',
    header: '',
    cell: () => (
      <div className="text-right">
        <Button variant="ghost" size="icon" className="h-[26px] w-[26px]">
          <MoreHorizontal className="h-3.5 w-3.5" />
        </Button>
      </div>
    ),
  },
];

export function BotAccountsTable({ data }: { data: BotAccount[] }) {
  return (
    <DataTable
      columns={columns}
      data={data}
      mobileLabel={col => (typeof col.header === 'string' ? col.header : '')}
    />
  );
}
```

- [ ] **Step 4: ModelsPage**

Replace `frontend/src/modules/superadmin/features/models/page.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import { Plus, Zap, RefreshCw, Eye } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { SlotCard } from './slot-card';
import { BotAccountsTable } from './bot-accounts-table';
import { slotsQuery, botAccountsQuery } from './api';

const SLOT_ICONS = { smart: RefreshCw, fast: Zap, vision: Eye } as const;

export default function ModelsPage() {
  const slots = useQuery(slotsQuery);
  const bots = useQuery(botAccountsQuery);

  return (
    <div className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1140px]">
      <header className="mb-8">
        <h1 className="text-[24px] font-semibold tracking-tight">Models &amp; Bots</h1>
        <p className="text-muted-foreground mt-1.5">
          Quản lý các model mặc định và bot account đang vận hành toàn hệ thống.
        </p>
      </header>

      <Tabs defaultValue="default" className="mb-6">
        <TabsList>
          <TabsTrigger value="default">Default models</TabsTrigger>
          <TabsTrigger value="bots">Bot accounts</TabsTrigger>
          <TabsTrigger value="providers">Providers &amp; keys</TabsTrigger>
        </TabsList>
      </Tabs>

      <section className="mb-11">
        <div className="flex items-end justify-between mb-3.5 gap-3 flex-wrap">
          <div>
            <h2 className="text-[14.5px] font-semibold tracking-tight">Model slots</h2>
            <p className="text-[12.5px] text-muted-foreground mt-0.5">Boss có thể override; đây là giá trị mặc định.</p>
          </div>
          <Button variant="ghost" size="sm">Reset to factory</Button>
        </div>
        {slots.isLoading ? (
          <div className="grid grid-cols-3 gap-3 max-md:grid-cols-1">
            {[0, 1, 2].map(i => <Skeleton key={i} className="h-[180px] rounded-[10px]" />)}
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-3 max-md:grid-cols-1">
            {slots.data?.map(s => (
              <SlotCard key={s.slot} slot={s} icon={SLOT_ICONS[s.slot]} />
            ))}
          </div>
        )}
      </section>

      <section className="mb-11">
        <div className="flex items-end justify-between mb-3.5 gap-3 flex-wrap">
          <div>
            <h2 className="text-[14.5px] font-semibold tracking-tight">Bot accounts</h2>
            <p className="text-[12.5px] text-muted-foreground mt-0.5">
              Tài khoản Zalo cá nhân và Telegram bot đang chạy.
            </p>
          </div>
          <Button>
            <Plus className="h-3.5 w-3.5" />
            Kết nối account
          </Button>
        </div>
        {bots.isLoading ? (
          <Skeleton className="h-[220px] rounded-[10px]" />
        ) : (
          <BotAccountsTable data={bots.data ?? []} />
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 5: Build + visual smoke test**

```bash
cd frontend && pnpm build && cd .. && ./scripts/restart.sh
```

Log in as superadmin, open `http://localhost:8000/app/superadmin/models`. Expected: 3 slot cards (Smart/Fast/Vision) populated from backend, bot accounts table populated. Theme toggle works. Resize to mobile → table converts to card list.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/modules/superadmin/
git commit -m "feat(frontend): superadmin Models & Bots page consuming /api/v1/superadmin/*"
```

---

### Task 15: Admin Group Note Viewer — full implementation

**Files:**
- Modify: `frontend/src/modules/admin/features/groups/group-detail.tsx` (real impl)
- Create: `frontend/src/modules/admin/features/groups/api.ts`
- Create: `frontend/src/modules/admin/features/groups/group-header.tsx`
- Create: `frontend/src/modules/admin/features/groups/summary-card.tsx`
- Create: `frontend/src/modules/admin/features/groups/items-list.tsx`
- Create: `frontend/src/modules/admin/features/groups/timeline-card.tsx`
- Create: `frontend/src/modules/admin/features/groups/right-panel.tsx`

- [ ] **Step 1: API layer**

Create `frontend/src/modules/admin/features/groups/api.ts`:

```ts
import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type Group = {
  id: number; name: string; channel: string;
  members_count: number; messages_30d: number; last_active_at: string | null;
};
export type Summary = { body: string | null; updated_at: string | null };
export type Item = {
  id: number; type: 'task' | 'reminder' | 'decision';
  text: string; assignee: string | null; due_at: string | null; created_at: string;
};
export type TimelineMsg = {
  id: number; author_name: string;
  author_kind: 'boss' | 'member' | 'bot';
  text: string; created_at: string; extracted?: string;
};
export type Stats = { messages: number; tasks: number; reminders: number; decisions: number };
export type Member = { id: number; name: string; role: string; last_seen_at: string | null };
export type File = { id: number; kind: 'doc' | 'link' | 'image'; name: string; url: string; created_at: string };

const base = (id: string) => `/api/v1/admin/groups/${id}`;

export const groupQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id], queryFn: () => api<Group>(base(id)),
});
export const summaryQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id, 'summary'],
  queryFn: () => api<Summary>(`${base(id)}/summary?date=today`),
});
export const itemsQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id, 'items'],
  queryFn: () => api<Item[]>(`${base(id)}/items?date=today`),
});
export const timelineQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id, 'timeline'],
  queryFn: () => api<{ messages: TimelineMsg[]; next_cursor: string | null }>(`${base(id)}/timeline?limit=20`),
});
export const statsQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id, 'stats'],
  queryFn: () => api<Stats>(`${base(id)}/stats?range=7d`),
});
export const membersQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id, 'members'],
  queryFn: () => api<Member[]>(`${base(id)}/members`),
});
export const filesQuery = (id: string) => queryOptions({
  queryKey: ['admin', 'group', id, 'files'],
  queryFn: () => api<File[]>(`${base(id)}/files?limit=10`),
});
```

- [ ] **Step 2: GroupHeader**

Create `frontend/src/modules/admin/features/groups/group-header.tsx`:

```tsx
import { Users, MessageSquare, Clock, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatNumber, relativeTime } from '@/lib/format';
import type { Group } from './api';

const CHANNEL_LABEL: Record<string, string> = {
  zalo: 'Zalo', telegram: 'Telegram', lark: 'Lark', web: 'Web',
};

export function GroupHeader({ group }: { group: Group }) {
  const initials = group.name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase();
  return (
    <div className="flex items-start gap-4 mb-7 flex-wrap">
      <div className="h-[52px] w-[52px] rounded-xl bg-gradient-to-br from-[hsl(168_60%_35%)] to-[hsl(220_50%_30%)] text-white text-lg font-semibold tracking-tight grid place-items-center shrink-0 shadow-[0_0_0_1px_hsl(168_40%_20%),inset_0_1px_0_hsl(168_80%_70%/0.2)]">
        {initials}
      </div>
      <div className="flex-1 min-w-[220px]">
        <h1 className="flex items-center gap-2.5 text-[22px] font-semibold tracking-tight">
          {group.name}
          <span className="text-[10.5px] py-0.5 px-1.5 rounded bg-muted text-muted-foreground font-medium tracking-wide uppercase">
            {CHANNEL_LABEL[group.channel] ?? group.channel}
          </span>
        </h1>
        <div className="text-[13px] text-muted-foreground flex items-center gap-3 flex-wrap mt-0.5">
          <span className="inline-flex items-center gap-1.5"><Users className="h-3.5 w-3.5 text-[hsl(var(--dim))]" />{group.members_count} thành viên</span>
          <span className="inline-flex items-center gap-1.5"><MessageSquare className="h-3.5 w-3.5 text-[hsl(var(--dim))]" />{formatNumber(group.messages_30d)} tin nhắn / 30 ngày</span>
          <span className="inline-flex items-center gap-1.5"><Clock className="h-3.5 w-3.5 text-[hsl(var(--dim))]" />Hoạt động cuối: {relativeTime(group.last_active_at)}</span>
        </div>
      </div>
      <div className="flex gap-1.5">
        <Button variant="ghost" size="sm"><Download className="h-3.5 w-3.5" />Xuất</Button>
        <Button variant="outline" size="sm">Cấu hình nhóm</Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: SummaryCard**

Create `frontend/src/modules/admin/features/groups/summary-card.tsx`:

```tsx
import { relativeTime } from '@/lib/format';
import type { Summary } from './api';

export function SummaryCard({ summary }: { summary: Summary }) {
  return (
    <div className="rounded-xl bg-card p-5 mb-5 relative overflow-hidden shadow-[0_0_0_1px_hsl(var(--border-strong)),0_1px_2px_rgba(0,0,0,.04)]">
      <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-gradient-to-b from-primary to-transparent opacity-50" />
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] uppercase tracking-wider text-primary font-medium inline-flex items-center gap-1.5 before:content-[''] before:h-1 before:w-1 before:rounded-full before:bg-primary">
          Tóm tắt hôm nay
        </span>
        <span className="text-xs text-[hsl(var(--dim))]">
          {summary.updated_at ? `Cập nhật ${relativeTime(summary.updated_at)}` : 'Chưa có'}
        </span>
      </div>
      {summary.body ? (
        <div
          className="text-sm leading-[1.7] whitespace-pre-wrap"
          dangerouslySetInnerHTML={{ __html: summary.body }}
        />
      ) : (
        <p className="text-sm text-muted-foreground">Chưa có tóm tắt cho hôm nay.</p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: ItemsList**

Create `frontend/src/modules/admin/features/groups/items-list.tsx`:

```tsx
import { User, Calendar } from 'lucide-react';
import { relativeTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Item } from './api';

const TAG_STYLE: Record<Item['type'], { label: string; cls: string }> = {
  task: { label: 'Tác vụ', cls: 'text-[hsl(var(--info))] bg-[hsl(var(--info)/0.1)]' },
  reminder: { label: 'Nhắc lịch', cls: 'text-[hsl(var(--warn))] bg-[hsl(var(--warn)/0.1)]' },
  decision: { label: 'Quyết định', cls: 'text-primary bg-[hsl(var(--primary)/0.1)]' },
};

export function ItemsList({ items }: { items: Item[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground py-8 text-center">Hôm nay chưa trích xuất mục nào.</p>;
  }
  return (
    <div className="flex flex-col gap-1.5">
      {items.map(it => {
        const tag = TAG_STYLE[it.type];
        return (
          <div key={`${it.type}-${it.id}`} className="flex items-start gap-2.5 py-2.5 px-3.5 bg-card rounded-lg shadow-[0_0_0_1px_hsl(var(--border-strong)),0_1px_2px_rgba(0,0,0,.04)] hover:bg-[hsl(var(--hover))] transition-colors cursor-pointer">
            <div className="h-4 w-4 rounded border-[1.5px] border-border-strong mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-[13.5px] tracking-tight mb-1">{it.text}</p>
              <div className="text-xs text-muted-foreground flex items-center gap-2.5 flex-wrap">
                <span className={cn('text-[10.5px] py-px px-1.5 rounded font-medium uppercase tracking-wide', tag.cls)}>{tag.label}</span>
                {it.assignee && (
                  <span className="inline-flex items-center gap-1"><User className="h-3 w-3" />{it.assignee}</span>
                )}
                {it.due_at && (
                  <span className="inline-flex items-center gap-1"><Calendar className="h-3 w-3" />{relativeTime(it.due_at)}</span>
                )}
              </div>
            </div>
            <span className="text-[11px] text-[hsl(var(--dim))] shrink-0 mt-0.5">{new Date(it.created_at).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 5: TimelineCard**

Create `frontend/src/modules/admin/features/groups/timeline-card.tsx`:

```tsx
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TimelineMsg } from './api';

export function TimelineCard({ messages }: { messages: TimelineMsg[] }) {
  if (messages.length === 0) {
    return <p className="text-sm text-muted-foreground py-8 text-center">Chưa có tin nhắn nào.</p>;
  }
  const groups = groupByDate(messages);
  return (
    <div className="rounded-xl bg-card shadow-[0_0_0_1px_hsl(var(--border-strong)),0_1px_2px_rgba(0,0,0,.04)] overflow-hidden">
      {groups.map(([date, msgs]) => (
        <div key={date}>
          <div className="px-[18px] py-2.5 bg-[hsl(var(--bg-subtle))] text-[11px] uppercase tracking-wide text-[hsl(var(--dim))] border-b border-border font-medium">
            {date}
          </div>
          {msgs.map(m => (
            <div key={m.id} className="px-[18px] py-3 border-b border-border last:border-b-0 flex gap-3">
              <Avatar kind={m.author_kind} name={m.author_name} />
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-2 mb-0.5">
                  <span className="text-[13px] font-medium tracking-tight">{m.author_name}</span>
                  <span className="text-[11px] text-[hsl(var(--dim))]">
                    {new Date(m.created_at).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
                <p className="text-[13.5px] leading-[1.55]">{m.text}</p>
                {m.extracted && (
                  <span className="mt-2 inline-flex items-center gap-1.5 text-[11.5px] text-primary px-2 py-[3px] bg-[hsl(var(--primary-soft))] rounded cursor-pointer">
                    <Check className="h-2.5 w-2.5" />
                    Đã trích: {m.extracted}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function Avatar({ kind, name }: { kind: TimelineMsg['author_kind']; name: string }) {
  const initial = (name[0] || '?').toUpperCase();
  return (
    <div className={cn(
      'h-7 w-7 rounded-full grid place-items-center font-medium text-[11px] tracking-tight shrink-0',
      kind === 'boss' && 'bg-gradient-to-br from-[hsl(280_50%_50%)] to-[hsl(320_50%_45%)] text-white',
      kind === 'bot' && 'bg-gradient-to-br from-[hsl(168_70%_45%)] to-[hsl(200_65%_45%)] text-white',
      kind === 'member' && 'bg-muted text-muted-foreground'
    )}>
      {initial}
    </div>
  );
}

function groupByDate(msgs: TimelineMsg[]): [string, TimelineMsg[]][] {
  const map = new Map<string, TimelineMsg[]>();
  for (const m of msgs) {
    const key = new Date(m.created_at).toLocaleDateString('vi-VN', { weekday: 'long', day: 'numeric', month: 'numeric' });
    map.set(key, [...(map.get(key) ?? []), m]);
  }
  return Array.from(map.entries());
}
```

- [ ] **Step 6: RightPanel**

Create `frontend/src/modules/admin/features/groups/right-panel.tsx`:

```tsx
import { FileText, LinkIcon, ImageIcon } from 'lucide-react';
import { formatNumber, relativeTime } from '@/lib/format';
import { StatusDot } from '@/components/status-dot';
import type { Stats, Member, File } from './api';

export function RightPanel({ stats, members, files }: { stats?: Stats; members?: Member[]; files?: File[] }) {
  return (
    <aside className="flex flex-col gap-4 sticky top-[90px] self-start">
      <Card title="7 ngày qua">
        <div className="grid grid-cols-2 gap-3">
          <Stat label="Tin nhắn" value={stats?.messages} />
          <Stat label="Tác vụ" value={stats?.tasks} />
          <Stat label="Nhắc lịch" value={stats?.reminders} />
          <Stat label="Quyết định" value={stats?.decisions} />
        </div>
      </Card>
      <Card title={`Thành viên (${members?.length ?? 0})`}>
        {members?.map((m, i) => (
          <div key={m.id} className={`flex items-center gap-2.5 py-1.5 ${i > 0 ? 'border-t border-border' : ''}`}>
            <div className="h-[26px] w-[26px] rounded-full bg-gradient-to-br from-[hsl(168_60%_40%)] to-[hsl(220_50%_35%)] text-white text-[10.5px] font-medium tracking-tight grid place-items-center shrink-0">
              {(m.name[0] || '?').toUpperCase()}
            </div>
            <div className="text-[12.5px] flex-1 min-w-0">
              {m.name} {m.role && <span className="text-[11px] text-[hsl(var(--dim))]">· {m.role}</span>}
            </div>
            <StatusDot status={m.last_seen_at ? 'ok' : 'idle'} />
          </div>
        ))}
      </Card>
      <Card title="Tệp & link gần đây">
        <div className="flex flex-col gap-2.5 text-[13px]">
          {files?.map(f => {
            const Icon = f.kind === 'image' ? ImageIcon : f.kind === 'link' ? LinkIcon : FileText;
            return (
              <div key={f.id} className="flex items-center gap-2 min-w-0">
                <Icon className="h-3.5 w-3.5 shrink-0 text-[hsl(var(--info))]" strokeWidth={2} />
                <span className="truncate">{f.name}</span>
                <span className="text-[11px] text-[hsl(var(--dim))] ml-auto shrink-0">{relativeTime(f.created_at)}</span>
              </div>
            );
          })}
        </div>
      </Card>
    </aside>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-[10px] bg-card p-4 shadow-[0_0_0_1px_hsl(var(--border-strong)),0_1px_2px_rgba(0,0,0,.04)]">
      <h3 className="text-[11px] uppercase tracking-wider text-[hsl(var(--dim))] font-medium mb-3">{title}</h3>
      {children}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div>
      <p className="text-xl font-semibold tracking-tight leading-tight">{value !== undefined ? formatNumber(value) : '—'}</p>
      <p className="text-[11px] text-muted-foreground mt-0.5">{label}</p>
    </div>
  );
}
```

- [ ] **Step 7: GroupDetail page**

Replace `frontend/src/modules/admin/features/groups/group-detail.tsx`:

```tsx
import { LoaderFunction, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { QueryClient } from '@tanstack/react-query';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { GroupHeader } from './group-header';
import { SummaryCard } from './summary-card';
import { ItemsList } from './items-list';
import { TimelineCard } from './timeline-card';
import { RightPanel } from './right-panel';
import {
  groupQuery, summaryQuery, itemsQuery, timelineQuery, statsQuery, membersQuery, filesQuery,
} from './api';

export const groupDetailLoader = (qc: QueryClient): LoaderFunction => async ({ params }) => {
  const id = params.groupId!;
  await qc.prefetchQuery(groupQuery(id));
  return { groupId: id };
};

export default function GroupDetail() {
  const { groupId } = useParams();
  const id = groupId!;
  const group = useQuery(groupQuery(id));
  const summary = useQuery(summaryQuery(id));
  const items = useQuery(itemsQuery(id));
  const timeline = useQuery(timelineQuery(id));
  const stats = useQuery(statsQuery(id));
  const members = useQuery(membersQuery(id));
  const files = useQuery(filesQuery(id));

  if (group.isLoading) {
    return <div className="p-10"><Skeleton className="h-32 w-full" /></div>;
  }
  if (!group.data) return null;

  return (
    <div className="px-10 py-8 max-md:px-4 max-md:py-6">
      <GroupHeader group={group.data} />

      <Tabs defaultValue="summary" className="mb-6">
        <TabsList>
          <TabsTrigger value="summary">Tóm tắt</TabsTrigger>
          <TabsTrigger value="timeline">Dòng thời gian</TabsTrigger>
          <TabsTrigger value="tasks">Tác vụ ({stats.data?.tasks ?? 0})</TabsTrigger>
          <TabsTrigger value="reminders">Nhắc lịch ({stats.data?.reminders ?? 0})</TabsTrigger>
          <TabsTrigger value="decisions">Quyết định ({stats.data?.decisions ?? 0})</TabsTrigger>
          <TabsTrigger value="files">Tệp &amp; link</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="grid grid-cols-[1fr_320px] gap-7 max-w-[1240px] max-md:grid-cols-1">
        <div>
          {summary.data && <SummaryCard summary={summary.data} />}
          <div className="flex items-center justify-between mt-7 mb-3.5">
            <h2 className="text-[13.5px] font-semibold tracking-tight">Mục được trích xuất hôm nay</h2>
          </div>
          {items.data && <ItemsList items={items.data} />}
          <div className="flex items-center justify-between mt-7 mb-3.5">
            <h2 className="text-[13.5px] font-semibold tracking-tight">Dòng thời gian</h2>
          </div>
          {timeline.data && <TimelineCard messages={timeline.data.messages} />}
        </div>
        <RightPanel stats={stats.data} members={members.data} files={files.data} />
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Build + visual smoke test**

```bash
cd frontend && pnpm build && cd .. && ./scripts/restart.sh
```

Log in as boss, open `/app/admin/groups/<seed-id>`. Expected: header + tabs + summary + items + timeline + right panel render with real data. Toggle theme. Resize to mobile.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/modules/admin/
git commit -m "feat(frontend): admin Group note viewer (header, summary, items, timeline, right panel)"
```

---

## Phase 7 — E2E tests + DoD verification

### Task 16: Playwright smoke tests + RBAC tests

**Files:**
- Create: `frontend/tests/smoke.spec.ts`
- Create: `frontend/tests/rbac.spec.ts`
- Create: `frontend/playwright.config.ts`
- Modify: `frontend/package.json` (add scripts)

- [ ] **Step 1: Install Playwright**

```bash
cd frontend
pnpm add -D @playwright/test
pnpm exec playwright install chromium
```

- [ ] **Step 2: Create `frontend/playwright.config.ts`**

```ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  use: { baseURL: 'http://localhost:8000', headless: true },
  webServer: {
    command: 'echo "assume backend running on :8000"',
    port: 8000,
    reuseExistingServer: true,
  },
});
```

- [ ] **Step 3: Create `frontend/tests/smoke.spec.ts`**

```ts
import { test, expect } from '@playwright/test';

// Assumes test backend has seeded a superadmin session token via env or fixture
test.describe('SPA smoke', () => {
  test('superadmin Models & Bots renders', async ({ page, context }) => {
    await context.addCookies([{
      name: 'session', value: process.env.E2E_SUPERADMIN_COOKIE!,
      domain: 'localhost', path: '/',
    }]);
    await page.goto('/app/superadmin/models');
    await expect(page.getByText('Models & Bots')).toBeVisible();
    await expect(page.getByText(/Smart|Fast|Vision/)).toBeVisible();
  });

  test('admin Group viewer renders', async ({ page, context }) => {
    await context.addCookies([{
      name: 'session', value: process.env.E2E_BOSS_COOKIE!,
      domain: 'localhost', path: '/',
    }]);
    await page.goto(`/app/admin/groups/${process.env.E2E_GROUP_ID}`);
    await expect(page.getByText(/thành viên/)).toBeVisible();
  });

  test('theme toggle works', async ({ page, context }) => {
    await context.addCookies([{
      name: 'session', value: process.env.E2E_BOSS_COOKIE!,
      domain: 'localhost', path: '/',
    }]);
    await page.goto('/app/admin/dashboard');
    const html = page.locator('html');
    const initial = await html.getAttribute('class');
    await page.getByLabel('Đổi theme').click();
    await expect(html).not.toHaveAttribute('class', initial ?? '');
  });
});
```

- [ ] **Step 4: Create `frontend/tests/rbac.spec.ts`**

```ts
import { test, expect } from '@playwright/test';

test.describe('RBAC routing', () => {
  test('boss redirected away from /superadmin/*', async ({ page, context }) => {
    await context.addCookies([{
      name: 'session', value: process.env.E2E_BOSS_COOKIE!,
      domain: 'localhost', path: '/',
    }]);
    await page.goto('/app/superadmin/models');
    await page.waitForURL(/\/app\/admin\//);
    expect(page.url()).toMatch(/\/app\/admin\//);
  });

  test('superadmin can access /admin/*', async ({ page, context }) => {
    await context.addCookies([{
      name: 'session', value: process.env.E2E_SUPERADMIN_COOKIE!,
      domain: 'localhost', path: '/',
    }]);
    await page.goto(`/app/admin/groups/${process.env.E2E_GROUP_ID}`);
    await expect(page.getByText(/thành viên/)).toBeVisible();
  });

  test('unauthenticated redirected to /login', async ({ page }) => {
    await page.goto('/app/admin/dashboard');
    await page.waitForURL(/\/login/);
    expect(page.url()).toContain('/login');
  });
});
```

- [ ] **Step 5: Add npm scripts**

In `frontend/package.json`, add to `"scripts"`:

```json
"e2e": "playwright test",
"lint": "eslint . --ext ts,tsx",
"typecheck": "tsc -b --noEmit"
```

- [ ] **Step 6: Run E2E (assumes backend + frontend built)**

```bash
# In separate shells / detached:
./scripts/restart.sh  # backend on :8000
cd frontend && pnpm build && cd ..  # ensure /app/* serves new bundle

# Provision E2E cookies (use the helper from existing test setup; reference tests/conftest.py)
# Then:
cd frontend && pnpm e2e
```

Expected: all 6 tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/tests/ frontend/playwright.config.ts frontend/package.json
git commit -m "test(frontend): Playwright smoke + RBAC tests"
```

---

### Task 17: CI script + DoD verification

**Files:**
- Modify: `frontend/package.json` (add `build:ci`)
- Create: `scripts/build_frontend.sh`

- [ ] **Step 1: Create `scripts/build_frontend.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm build
echo "Frontend built → src/web/static/app/"
```

```bash
chmod +x scripts/build_frontend.sh
```

- [ ] **Step 2: Run full DoD checklist**

Walk through Section 9 of the spec:
- `cd frontend && pnpm lint && pnpm typecheck && pnpm build` → no errors.
- Backend tests `pytest tests/integration/test_api_me.py tests/integration/test_api_superadmin.py tests/integration/test_api_admin_groups.py -v` → all pass.
- E2E `pnpm e2e` → all 6 pass.
- Manual: login flow, both sample pages, theme toggle, sidebar collapse, mobile drawer, user dropdown — every interaction works in browser. No console errors.
- Resize to 360 / 768 / 1280 → no layout break, table converts to card list at < 720px.
- Legacy `/legacy-app/*` still works (sanity check one route, e.g. `/legacy-app/dashboard`).

- [ ] **Step 3: Commit**

```bash
git add scripts/build_frontend.sh
git commit -m "chore(ci): scripts/build_frontend.sh for lint+typecheck+build"
```

---

## Coverage check vs spec

| Spec section | Implemented by |
|---|---|
| 1 Mục tiêu / scope SP1 | Tasks 1-17 |
| 2 Stack | Task 1, 2, 3 |
| 3 Repo layout | Task 1, 12 |
| 3 Build pipeline | Task 1, 4, 17 |
| 4 Auth + RBAC | Task 4, 5, 8 (rbac.ts), 12 (loaders) |
| 5 Design tokens | Task 2 |
| 6 Component primitives | Task 3 (shadcn), 9, 10, 11 |
| 7.1 Super-admin Models & Bots | Task 6 (API), 14 (UI) |
| 7.2 Admin Group viewer | Task 7 (API), 15 (UI) |
| 8 Responsive | Task 10, 14, 15 (all responsive via Tailwind breakpoints) |
| 9 Testing / DoD | Task 16, 17 |
| 10 Migration outlook | (deferred to SP2 spec) |
| 11 Risks | Pre-flight note + Task 4 (legacy-app rename) |

Open notes for SP2:
- Audit each Jinja2 page in `src/web/templates/` and map to its required API endpoints.
- Login page port to React (currently relies on Jinja2 `/login`).
- Replace `User #{me.id}` with real `name` + `email` once `/api/v1/me` returns them (small backend extension).
