# Admin Dashboard Polish — Design Spec

**Date:** 2026-06-07
**Scope:** `/app/admin/dashboard` only. Page is the canonical reference; other admin pages clone the pattern in later phases.

## Goal

Polish the boss dashboard so it looks "xịn" — refined Linear/Vercel aesthetic, alive but not flashy, mobile-clean, ⌘K search working. The page becomes the visual baseline for the rest of the app.

## Non-Goals

- Touching other pages (action-items, groups, reminders, settings, …)
- Public landing / signup
- Project-wide i18n sweep (only dashboard strings normalized)
- Server-side global search (⌘K returns local commands only this phase)

## Design Decisions (confirmed)

| Decision | Choice |
|---|---|
| Visual direction | **A · Linear / Vercel** — sharp, dark-first, snappy |
| Accent | **Teal → Cyan** (refined version of current) |
| Animation depth | **L2** — micro + entrance stagger + page transition + count-up |
| Layout | **Refined current** — greeting → 4 stats → 2-col → activity feed |
| Animation library | `framer-motion` (~30 KB gz) |

## Changes

### 1. Design tokens — `frontend/src/styles/globals.css`

Refine the existing HSL token system; do not switch palettes.

- **Background scale (dark):** `--background 240 8% 5%`, `--bg-subtle 240 7% 7%`, `--card 240 7% 9%`, `--hover 240 6% 12%`. Slightly deeper than current for more contrast against accent.
- **Border scale:** `--border 240 6% 14%`, `--border-strong 240 6% 19%`.
- **Primary:** `--primary 172 70% 45%` (teal-cyan midpoint), `--primary-strong 188 80% 50%` (cyan), `--primary-soft 172 50% 14%`. Accent gradient = `linear-gradient(135deg, hsl(var(--primary)), hsl(var(--primary-strong)))`.
- **Type scale tokens:** add `--text-xs .6875rem` (11px), `--text-sm .78125rem` (12.5px), `--text-base .84375rem` (13.5px), `--text-lg .9375rem` (15px), `--text-xl 1.125rem` (18px), `--text-2xl 1.375rem` (22px), `--text-3xl 1.75rem` (28px). Heading tracking `-0.02em`.
- **Radii:** `--radius 8px` (default), keep current 6 / 10 / 14 inline where used.
- **Shadows:** add utility classes `.shadow-ring` (1px border ring) and `.shadow-pop` (`0 8px 24px -12px hsl(0 0% 0% / 0.5)`).
- **Light mode:** keep `.light` class; rebalance so primary stays readable on white (lower lightness on accent, raise saturation).

### 2. Component primitives

Touch only what dashboard renders. Files in `frontend/src/components/ui/`.

- `button.tsx` — refine variants. Hover: `translateY(-1px)`, active: `scale(0.98)`. Focus ring: 2px teal. Transition 150 ms.
- `card.tsx` — **new**, replacing inline `rounded-[12px] border bg-card`. Variants: `default` (border + bg), `glow` (border + subtle radial glow corner for stat cards). Top inner highlight: `inset 0 1px 0 hsl(0 0% 100% / 0.04)`.
- `badge.tsx` — restyle pill: tighter padding, monospace numerics inside, `live` variant with pulse dot.
- `skeleton.tsx` — shimmer gradient sweep (replace static `animate-pulse`).
- `kbd.tsx` — **new** for `⌘K` keycap display.

No other primitives are touched.

### 3. Dashboard page — `frontend/src/modules/admin/features/dashboard/page.tsx`

Rewrite the page top to bottom. Same data contract, richer presentation.

**Sections, top to bottom:**

1. **Hero greeting** — `Chào buổi sáng/chiều/tối, boss.` Weight 600, tracking -0.02em. "boss" rendered with accent gradient text. Subtitle `Tổng quan workspace · 30 ngày qua`.
2. **4 stat cards** — grid `grid-cols-2 md:grid-cols-4 gap-3`. Each card:
   - Uppercase label (10 px, dim, letter-spaced)
   - Big number with **count-up** animation on mount (framer-motion `useMotionValue` + `animate`, duration 1.0 s, ease `[0.2, 0.7, 0.2, 1]`)
   - **Delta %** vs previous 30 days (`↗ +N%` green / `↘ -N%` rose / `→ 0%` dim) — needs small backend addition (§5)
   - Subtle radial glow in bottom-right corner (the accent color, low alpha)
   - Icon dropped (was redundant with label) — replaced with a 1×24 accent strip at top of card for visual rhythm
3. **2-col grid** (`md:grid-cols-2 gap-3`):
   - **Nhóm gần đây** — list, each row hover translates right 2 px, shows `relativeTime` + `provider` pill. Provider colors tied to tokens (no hardcoded blue/sky).
   - **Việc cần làm hôm nay** — list, due time on right. Empty state: icon + text + small CTA "Tạo nhóm đầu tiên" / "Hôm nay rảnh, nghỉ thôi 🙂" (no other emoji elsewhere).
4. **Activity feed** — full-width card. "Realtime" badge with pulse dot in header. Each row: kind pill + title + relative time. Hover lift.

**Motion:**

- Entrance: hero (delay 0) → stats stagger (80 ms each, fadeUp 8 px) → grid (delay 0.32 s) → feed (delay 0.5 s). Total ≈ 0.7 s.
- All `prefers-reduced-motion: reduce` → animations become instant (use framer-motion's `useReducedMotion`).
- Loading skeleton: shape-matched (greeting, 4 stat boxes, 2-col, feed) — no generic blocks.
- Error state: card with retry button (calls `refetch()` instead of just text).

**Strings:** all Vietnamese, consistent tone. No English mixed in body copy.

### 4. ⌘K command palette — wire `cmdk`

Already in `package.json`. Two new files:

- `frontend/src/components/command-palette.tsx` — `<CommandDialog>` wrapper with `cmdk` primitives, styled to match.
- `frontend/src/lib/use-command-palette.ts` — hook providing open state + register-command API, listens for `⌘K` / `Ctrl+K` globally.

Commands registered for this phase (static, no fetch):

- **Trang** group: Dashboard / Việc cần làm / Nhắc nhở / Nhóm / Dự án / Settings (driven by `adminNav`)
- **Hành động** group: Chuyển sang light/dark theme, Đăng xuất
- **Hôm nay** group: top 5 of `today_items` (read from React Query cache so no re-fetch)

`AppShell` topbar search button opens the dialog. Mobile: tap opens too (no keyboard hint shown <sm).

### 5. Backend — `src/web/routes/api_admin.py::get_dashboard`

Single additive change: return previous-30-day counts so the client can show delta %.

```python
"stats_30d": { ... existing ... },
"stats_prev_30d": {
    "messages": int(prev_msg_count or 0),
    "tasks": int(prev_task_count or 0),
    "reminders": int(prev_reminder_count or 0),
    "decisions": int(prev_decision_count or 0),
},
```

Four extra `fetchval` calls with `ts >= now - 60d AND ts < now - 30d`. Tests in `tests/api/test_admin_dashboard.py` updated to assert the new keys exist and are integers ≥ 0.

Sparkline data (per-day series) is **deferred** — count-up + delta % is enough visual signal for this phase.

### 6. Mobile responsiveness

- Breakpoint: standard `md` (768 px).
- Stats: `grid-cols-2 md:grid-cols-4`. Each card same height on mobile (no shrink-to-fit ugliness).
- 2-col groups: stacks below `md`. Active "today items" list shown first (above groups) on mobile.
- Topbar: search button → icon-only `<md`, `⌘K` hint hidden. Sidebar collapse hidden `<md` (uses drawer).
- Drawer: framer-motion `motion.aside` with spring `{ stiffness: 280, damping: 30 }`, backdrop blur kept.

### 7. Animation library + presets — `frontend/src/lib/motion.ts` (new)

```ts
export const ease = [0.2, 0.7, 0.2, 1] as const;
export const fadeUp = {
  hidden: { opacity: 0, y: 8 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.35, ease } },
};
export const staggerContainer = (gap = 0.08, delay = 0) => ({
  hidden: {},
  show:   { transition: { staggerChildren: gap, delayChildren: delay } },
});
export const pageTransition = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.25, ease } },
  exit:    { opacity: 0, y: -4, transition: { duration: 0.15, ease } },
};
export const spring = { type: 'spring', stiffness: 280, damping: 30 } as const;
```

`AdminLayout` wraps `<Outlet />` in `<AnimatePresence mode="wait">` with `pageTransition` keyed by `location.pathname`.

## Testing

- Manual: open `/app/admin/dashboard` in both light + dark, in Chrome / mobile viewport. Verify: count-up runs once, no layout shift, ⌘K opens/closes, reduced-motion disables animations.
- Backend: extend `tests/api/test_admin_dashboard.py` to assert `stats_prev_30d` shape.
- Frontend: existing Playwright e2e (`tests/e2e/`) — add one smoke test "dashboard renders without console errors and ⌘K opens palette."

## Files Touched

```
docs/superpowers/specs/2026-06-07-admin-dashboard-polish-design.md   (this)
frontend/package.json                                                 (+framer-motion)
frontend/src/styles/globals.css                                       (tokens refined)
frontend/src/components/ui/button.tsx                                 (variants refined)
frontend/src/components/ui/card.tsx                                   NEW
frontend/src/components/ui/badge.tsx                                  (variants refined)
frontend/src/components/ui/skeleton.tsx                               (shimmer)
frontend/src/components/ui/kbd.tsx                                    NEW
frontend/src/components/app-shell.tsx                                 (search wired, mobile drawer motion)
frontend/src/components/command-palette.tsx                           NEW
frontend/src/lib/use-command-palette.ts                               NEW
frontend/src/lib/motion.ts                                            NEW
frontend/src/modules/admin/layout.tsx                                 (AnimatePresence wrap)
frontend/src/modules/admin/features/dashboard/page.tsx                rewrite
src/web/routes/api_admin.py                                           (+stats_prev_30d)
tests/api/test_admin_dashboard.py                                     (assert new keys)
tests/e2e/<dashboard smoke spec>                                      (new or extend)
```

## Risks & Trade-offs

- **Bundle size**: +~30 KB gz for framer-motion. Acceptable for the polish gain; no other heavy adds.
- **Token refactor blast radius**: globals.css changes affect every page. Audit done — other pages already use HSL token variables, so they shift visually but should not break. Other-page polish in later phases will clean up any residual ugliness.
- **Delta % look weird when previous period was 0** (`+∞%`). Render as `Mới` (new) in that case.
