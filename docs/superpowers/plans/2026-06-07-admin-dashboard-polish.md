# Admin Dashboard Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish `/app/admin/dashboard` end-to-end (tokens, motion, ⌘K, mobile) so it becomes the canonical visual reference for the app.

**Architecture:** Refine existing Vite + React 19 + Tailwind v4 + Radix/shadcn stack. Tokens live in `globals.css`; motion presets in `lib/motion.ts`; framer-motion adds entrance stagger, count-up, page transition; `cmdk` (already a dep) is wired through a new `command-palette.tsx` + a `use-command-palette` hook; backend gets one additive field (`stats_prev_30d`) for delta %.

**Tech Stack:** TypeScript, React 19, Vite 8, Tailwind v4, `@radix-ui/*`, `cmdk`, `framer-motion` (new), FastAPI, asyncpg, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-06-07-admin-dashboard-polish-design.md`

---

## File Map

**New files:**
- `frontend/src/lib/motion.ts` — framer-motion presets (`fadeUp`, `staggerContainer`, `pageTransition`, `spring`).
- `frontend/src/components/ui/card.tsx` — Card primitive with `default` and `glow` variants.
- `frontend/src/components/ui/kbd.tsx` — Keycap display for `⌘K`.
- `frontend/src/components/command-palette.tsx` — Wired CommandDialog with grouped commands.
- `frontend/src/lib/use-command-palette.ts` — Open-state hook + global key listener.
- `frontend/src/modules/admin/features/dashboard/components/stat-card.tsx` — Stat card with count-up + delta.
- `frontend/src/modules/admin/features/dashboard/components/recent-groups.tsx` — Groups list block.
- `frontend/src/modules/admin/features/dashboard/components/today-items.tsx` — Today items block.
- `frontend/src/modules/admin/features/dashboard/components/activity-feed.tsx` — Activity feed block.
- `frontend/src/modules/admin/features/dashboard/components/dashboard-skeleton.tsx` — Shape-matched skeleton.

**Modified files:**
- `frontend/package.json` — `+ "framer-motion": "^12.x"`.
- `frontend/src/styles/globals.css` — token rewrite (colors, type scale, radii, shadow utilities).
- `frontend/src/components/ui/button.tsx` — hover/active micro, focus ring update.
- `frontend/src/components/ui/badge.tsx` — `live` variant + token alignment.
- `frontend/src/components/ui/skeleton.tsx` — shimmer sweep.
- `frontend/src/components/app-shell.tsx` — wire ⌘K open, mobile drawer spring, search icon-only on mobile.
- `frontend/src/modules/admin/layout.tsx` — wrap `<Outlet />` in `<AnimatePresence>` with `pageTransition`.
- `frontend/src/modules/admin/features/dashboard/page.tsx` — full rewrite into composition of the new component files.
- `src/web/routes/api_admin.py` — append `stats_prev_30d` block to `get_dashboard`.
- `tests/integration/test_api_admin_dashboard.py` — assert `stats_prev_30d` shape.
- `frontend/tests/admin-flow.spec.ts` — add ⌘K palette open smoke.

---

## Task 1: Install framer-motion + motion presets

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/lib/motion.ts`

- [ ] **Step 1: Add framer-motion to package.json**

In `frontend/package.json` `dependencies`, insert (alphabetical order between `cmdk` and `lucide-react`):

```json
"framer-motion": "^12.0.0",
```

- [ ] **Step 2: Install**

Run (cwd = `frontend/`):
```bash
pnpm install
```
Expected: pnpm-lock.yaml updates, no peer warnings beyond existing.

- [ ] **Step 3: Create motion presets**

Write `frontend/src/lib/motion.ts`:

```ts
import type { Transition, Variants } from 'framer-motion';

export const ease = [0.2, 0.7, 0.2, 1] as const;

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 8 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.35, ease } },
};

export const staggerContainer = (gap = 0.08, delay = 0): Variants => ({
  hidden: {},
  show:   { transition: { staggerChildren: gap, delayChildren: delay } },
});

export const pageTransition = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.25, ease } },
  exit:    { opacity: 0, y: -4, transition: { duration: 0.15, ease } },
};

export const spring: Transition = { type: 'spring', stiffness: 280, damping: 30 };
```

- [ ] **Step 4: Typecheck**

Run (cwd = `frontend/`):
```bash
pnpm typecheck
```
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src/lib/motion.ts
git commit -m "feat(frontend): add framer-motion + shared motion presets"
```

---

## Task 2: Refine design tokens in `globals.css`

**Files:**
- Modify: `frontend/src/styles/globals.css`

- [ ] **Step 1: Rewrite token blocks**

Replace the `:root { ... }` and `.light { ... }` blocks (currently lines ~16–55) with:

```css
:root {
  --background: 240 8% 5%;
  --bg-subtle: 240 7% 7%;
  --foreground: 0 0% 98%;
  --muted: 240 5% 11%;
  --muted-foreground: 240 5% 62%;
  --dim: 240 4% 40%;
  --border: 240 6% 14%;
  --border-strong: 240 6% 19%;
  --card: 240 7% 9%;
  --hover: 240 6% 12%;
  --primary: 172 70% 45%;
  --primary-strong: 188 80% 50%;
  --primary-soft: 172 50% 14%;
  --primary-foreground: 170 80% 6%;
  --danger: 0 62% 60%;
  --ok: 158 60% 50%;
  --warn: 38 88% 60%;
  --info: 210 80% 65%;
  --radius: 8px;
  --text-xs: .6875rem;
  --text-sm: .78125rem;
  --text-base: .84375rem;
  --text-lg: .9375rem;
  --text-xl: 1.125rem;
  --text-2xl: 1.375rem;
  --text-3xl: 1.75rem;
}

.light {
  --background: 0 0% 100%;
  --bg-subtle: 240 10% 98.5%;
  --foreground: 240 10% 4%;
  --muted: 240 5% 96%;
  --muted-foreground: 240 4% 38%;
  --dim: 240 4% 58%;
  --border: 240 6% 92%;
  --border-strong: 240 6% 84%;
  --card: 0 0% 100%;
  --hover: 240 5% 96%;
  --primary: 172 78% 32%;
  --primary-strong: 188 85% 38%;
  --primary-soft: 172 60% 94%;
  --primary-foreground: 0 0% 100%;
  --info: 210 80% 50%;
  --ok: 158 60% 38%;
  --warn: 38 88% 42%;
  --danger: 0 62% 50%;
}
```

- [ ] **Step 2: Add shadow & gradient utilities**

Append at the end of `globals.css`:

```css
@layer utilities {
  .shadow-ring {
    box-shadow: 0 0 0 1px hsl(var(--border));
  }
  .shadow-pop {
    box-shadow: 0 8px 24px -12px hsl(0 0% 0% / 0.55);
  }
  .text-accent-gradient {
    background: linear-gradient(135deg, hsl(var(--primary)), hsl(var(--primary-strong)));
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    color: transparent;
  }
  .bg-accent-gradient {
    background: linear-gradient(135deg, hsl(var(--primary)), hsl(var(--primary-strong)));
  }
}
```

- [ ] **Step 3: Verify build**

Run (cwd = `frontend/`):
```bash
pnpm build
```
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/styles/globals.css
git commit -m "style(frontend): refine design tokens (teal/cyan, type scale, shadow utils)"
```

---

## Task 3: Add `card.tsx` + `kbd.tsx` primitives

**Files:**
- Create: `frontend/src/components/ui/card.tsx`
- Create: `frontend/src/components/ui/kbd.tsx`

- [ ] **Step 1: Write `card.tsx`**

```tsx
import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const cardVariants = cva(
  'rounded-[12px] border bg-card transition-colors',
  {
    variants: {
      variant: {
        default: 'border-border',
        glow: 'border-border relative overflow-hidden before:absolute before:inset-0 before:pointer-events-none before:bg-[radial-gradient(120px_60px_at_100%_100%,hsl(var(--primary)/0.10),transparent_70%)]',
      },
    },
    defaultVariants: { variant: 'default' },
  }
);

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant, ...props }, ref) => (
    <div ref={ref} className={cn(cardVariants({ variant }), className)} {...props} />
  )
);
Card.displayName = 'Card';

export const CardHeader = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('px-4 py-3 border-b border-border flex items-center justify-between gap-2', className)} {...p} />
);
export const CardTitle = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <h3 className={cn('text-[13px] font-semibold tracking-tight', className)} {...p} />
);
export const CardBody = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('px-4 py-3', className)} {...p} />
);
```

- [ ] **Step 2: Write `kbd.tsx`**

```tsx
import * as React from 'react';
import { cn } from '@/lib/utils';

export const Kbd = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(
  ({ className, children, ...props }, ref) => (
    <kbd
      ref={ref}
      className={cn(
        'inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-[4px]',
        'border border-border bg-muted px-1 font-mono text-[10px] text-[hsl(var(--dim))]',
        className
      )}
      {...props}
    >
      {children}
    </kbd>
  )
);
Kbd.displayName = 'Kbd';
```

- [ ] **Step 3: Typecheck**

```bash
pnpm typecheck
```
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ui/card.tsx frontend/src/components/ui/kbd.tsx
git commit -m "feat(frontend): add Card and Kbd UI primitives"
```

---

## Task 4: Refine `button.tsx`, `badge.tsx`, `skeleton.tsx`

**Files:**
- Modify: `frontend/src/components/ui/button.tsx`
- Modify: `frontend/src/components/ui/badge.tsx`
- Modify: `frontend/src/components/ui/skeleton.tsx`

- [ ] **Step 1: Replace `button.tsx` contents**

```tsx
import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-[12.5px] font-medium',
    'transition-[transform,background-color,box-shadow,color] duration-150',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.55)]',
    'active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50',
    '[&_svg]:pointer-events-none [&_svg]:size-3.5 [&_svg]:shrink-0',
  ].join(' '),
  {
    variants: {
      variant: {
        default:
          'bg-accent-gradient text-[hsl(var(--primary-foreground))] shadow-pop hover:-translate-y-[1px]',
        destructive:
          'bg-[hsl(var(--danger))] text-white shadow-pop hover:-translate-y-[1px]',
        outline:
          'border border-border bg-transparent text-foreground hover:bg-[hsl(var(--hover))] hover:-translate-y-[1px]',
        secondary:
          'bg-[hsl(var(--muted))] text-foreground hover:bg-[hsl(var(--hover))]',
        ghost: 'hover:bg-[hsl(var(--hover))] text-foreground',
        link: 'text-[hsl(var(--primary))] underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-8 px-3',
        sm: 'h-7 px-2.5 text-[11px]',
        lg: 'h-9 px-4',
        icon: 'h-8 w-8',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size, className }))} {...props} />;
  }
);
Button.displayName = 'Button';

export { Button, buttonVariants };
```

- [ ] **Step 2: Replace `badge.tsx` contents**

```tsx
import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-[4px] px-1.5 py-[1px] text-[10px] font-medium tabular-nums',
  {
    variants: {
      variant: {
        default: 'bg-[hsl(var(--primary-soft))] text-[hsl(var(--primary))]',
        secondary: 'bg-[hsl(var(--muted))] text-muted-foreground',
        outline: 'border border-border text-muted-foreground',
        destructive: 'bg-[hsl(var(--danger)/0.15)] text-[hsl(var(--danger))]',
        live: 'bg-[hsl(var(--primary-soft))] text-[hsl(var(--primary))]',
      },
    },
    defaultVariants: { variant: 'default' },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, children, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props}>
      {variant === 'live' && (
        <span className="relative inline-flex h-1.5 w-1.5">
          <span className="absolute inset-0 rounded-full bg-[hsl(var(--primary))] opacity-60 animate-ping" />
          <span className="relative rounded-full bg-[hsl(var(--primary))] h-1.5 w-1.5" />
        </span>
      )}
      {children}
    </div>
  );
}

export { Badge, badgeVariants };
```

- [ ] **Step 3: Replace `skeleton.tsx` contents**

```tsx
import { cn } from '@/lib/utils';

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-md bg-[hsl(var(--muted))]',
        'before:absolute before:inset-0 before:-translate-x-full',
        'before:bg-gradient-to-r before:from-transparent before:via-white/[0.04] before:to-transparent',
        'before:animate-[shimmer_1.6s_ease-in-out_infinite]',
        className
      )}
      {...props}
    />
  );
}

export { Skeleton };
```

- [ ] **Step 4: Register shimmer keyframe**

Append to `frontend/src/styles/globals.css` (inside or after `@layer utilities`):

```css
@keyframes shimmer {
  100% { transform: translateX(100%); }
}
```

- [ ] **Step 5: Verify**

```bash
pnpm typecheck && pnpm build
```
Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ui/button.tsx frontend/src/components/ui/badge.tsx frontend/src/components/ui/skeleton.tsx frontend/src/styles/globals.css
git commit -m "style(frontend): refine button/badge/skeleton primitives"
```

---

## Task 5: Backend — add `stats_prev_30d` to dashboard endpoint (TDD)

**Files:**
- Modify: `tests/integration/test_api_admin_dashboard.py`
- Modify: `src/web/routes/api_admin.py`

- [ ] **Step 1: Add failing test**

In `tests/integration/test_api_admin_dashboard.py`, inside `test_dashboard_returns_expected_shape`, after the existing `stats_30d` assertions block (around line 45), insert:

```python
    # stats_prev_30d shape — counts for 60→30 days ago
    prev = body["stats_prev_30d"]
    assert "messages" in prev
    assert "tasks" in prev
    assert "reminders" in prev
    assert "decisions" in prev
    assert all(isinstance(prev[k], int) for k in ("messages", "tasks", "reminders", "decisions"))
    assert all(prev[k] >= 0 for k in ("messages", "tasks", "reminders", "decisions"))
```

- [ ] **Step 2: Run — verify it fails**

```bash
pytest tests/integration/test_api_admin_dashboard.py::test_dashboard_returns_expected_shape -v
```
Expected: FAIL with `KeyError: 'stats_prev_30d'`.

- [ ] **Step 3: Implement in `api_admin.py::get_dashboard`**

In `src/web/routes/api_admin.py`:

(a) Near the top of `get_dashboard`, where `thirty_days_ago = now - timedelta(days=30)` is defined, add:

```python
    sixty_days_ago = now - timedelta(days=60)
```

(b) Inside the `async with db.acquire() as c:` block, after the existing `decision_count = await c.fetchval(...)` query (around line 86), add:

```python
        # Previous 30-day window (60d → 30d ago) for delta %
        prev_msg_count = await c.fetchval(
            "SELECT count(*) FROM messages WHERE boss_id=$1 AND ts >= $2 AND ts < $3",
            ctx.boss_id, sixty_days_ago, thirty_days_ago,
        )
        prev_task_count = await c.fetchval(
            "SELECT count(*) FROM action_items WHERE boss_id=$1 AND created_at >= $2 AND created_at < $3",
            ctx.boss_id, sixty_days_ago, thirty_days_ago,
        )
        prev_reminder_count = await c.fetchval(
            "SELECT count(*) FROM scheduled_reminders WHERE boss_id=$1 AND created_at >= $2 AND created_at < $3",
            ctx.boss_id, sixty_days_ago, thirty_days_ago,
        )
        prev_decision_count = await c.fetchval(
            """
            SELECT count(*) FROM decisions d
            JOIN group_notes gn ON gn.id = d.group_id
            WHERE gn.boss_id = $1 AND d.created_at >= $2 AND d.created_at < $3
            """,
            ctx.boss_id, sixty_days_ago, thirty_days_ago,
        )
```

(c) In the returned dict, add the `stats_prev_30d` key right after `stats_30d`:

```python
        "stats_prev_30d": {
            "messages": int(prev_msg_count or 0),
            "tasks": int(prev_task_count or 0),
            "reminders": int(prev_reminder_count or 0),
            "decisions": int(prev_decision_count or 0),
        },
```

- [ ] **Step 4: Run test — verify pass**

```bash
pytest tests/integration/test_api_admin_dashboard.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/web/routes/api_admin.py tests/integration/test_api_admin_dashboard.py
git commit -m "feat(api-admin): return stats_prev_30d for delta % comparison"
```

---

## Task 6: Command palette — hook + component

**Files:**
- Create: `frontend/src/lib/use-command-palette.ts`
- Create: `frontend/src/components/command-palette.tsx`

- [ ] **Step 1: Write the hook**

```ts
// frontend/src/lib/use-command-palette.ts
import { create } from 'zustand';
import { useEffect } from 'react';

type State = { open: boolean; setOpen: (v: boolean) => void; toggle: () => void };

export const useCommandPalette = create<State>((set) => ({
  open: false,
  setOpen: (v) => set({ open: v }),
  toggle: () => set((s) => ({ open: !s.open })),
}));

export function useCommandPaletteHotkey() {
  const toggle = useCommandPalette((s) => s.toggle);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [toggle]);
}
```

> **Note:** If `zustand` is not yet installed, replace the file with a plain React Context-based store. To check, run `pnpm list zustand` (cwd `frontend/`). If absent, install with `pnpm add zustand` and commit `package.json` + `pnpm-lock.yaml` in this task.

- [ ] **Step 2: Verify or install `zustand`**

```bash
pnpm list zustand
```
If "no matches": `pnpm add zustand`.

- [ ] **Step 3: Write the palette component**

```tsx
// frontend/src/components/command-palette.tsx
import { useNavigate } from 'react-router-dom';
import { useTheme } from 'next-themes';
import { LogOut, SunMoon, Search } from 'lucide-react';
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command';
import { useCommandPalette } from '@/lib/use-command-palette';
import type { NavSection } from '@/components/app-shell';

export function CommandPalette({ nav }: { nav: NavSection[] }) {
  const open = useCommandPalette((s) => s.open);
  const setOpen = useCommandPalette((s) => s.setOpen);
  const navigate = useNavigate();
  const { theme, setTheme } = useTheme();

  const go = (href: string) => {
    setOpen(false);
    navigate(href);
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Tìm trang, hành động…" />
      <CommandList>
        <CommandEmpty>Không tìm thấy.</CommandEmpty>
        {nav.map((section) => (
          <CommandGroup key={section.label} heading={section.label}>
            {section.items.map((item) => (
              <CommandItem key={item.href} onSelect={() => go(item.href)}>
                <item.icon className="h-4 w-4" />
                <span>{item.label}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
        <CommandSeparator />
        <CommandGroup heading="Hành động">
          <CommandItem
            onSelect={() => {
              setTheme(theme === 'light' ? 'dark' : 'light');
              setOpen(false);
            }}
          >
            <SunMoon className="h-4 w-4" />
            <span>Đổi chế độ sáng/tối</span>
          </CommandItem>
          <CommandItem
            onSelect={() => {
              setOpen(false);
              window.location.href = '/logout';
            }}
          >
            <LogOut className="h-4 w-4" />
            <span>Đăng xuất</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
```

- [ ] **Step 4: Typecheck**

```bash
pnpm typecheck
```
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/use-command-palette.ts frontend/src/components/command-palette.tsx frontend/package.json frontend/pnpm-lock.yaml
git commit -m "feat(frontend): add ⌘K command palette (page nav + theme + logout)"
```

---

## Task 7: Wire ⌘K into `AppShell` + mobile drawer spring

**Files:**
- Modify: `frontend/src/components/app-shell.tsx`

- [ ] **Step 1: Patch `app-shell.tsx`**

Replace the file contents with:

```tsx
import { useState } from 'react';
import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronLeft, Menu, Search, type LucideIcon } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Kbd } from '@/components/ui/kbd';
import { ThemeToggle } from './theme-toggle';
import { UserMenu } from './user-menu';
import { CommandPalette } from './command-palette';
import { useCommandPalette, useCommandPaletteHotkey } from '@/lib/use-command-palette';
import type { Me } from '@/lib/auth';
import { cn } from '@/lib/utils';
import { spring } from '@/lib/motion';

export type NavItem = { label: string; href: string; icon: LucideIcon };
export type NavSection = { label: string; items: NavItem[] };

export function AppShell({
  nav, me, breadcrumb, children,
}: {
  nav: NavSection[];
  me: Me;
  breadcrumb: ReactNode;
  children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const setPaletteOpen = useCommandPalette((s) => s.setOpen);
  useCommandPaletteHotkey();
  const sb = collapsed ? '60px' : '232px';

  return (
    <div
      className="relative grid min-h-screen transition-[grid-template-columns] duration-200 md:grid-cols-[var(--sb)_1fr]"
      style={{ ['--sb' as string]: sb }}
    >
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            key="backdrop"
            className="md:hidden fixed inset-0 bg-black/60 backdrop-blur-sm z-20"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={() => setMobileOpen(false)}
          />
        )}
      </AnimatePresence>

      <motion.aside
        className={cn(
          'flex flex-col border-r border-border bg-card relative z-30',
          'md:static md:translate-x-0 md:w-auto md:min-w-0',
          'fixed inset-y-0 left-0 w-[260px]'
        )}
        animate={{ x: mobileOpen ? 0 : (typeof window !== 'undefined' && window.innerWidth < 768 ? -260 : 0) }}
        transition={spring}
      >
        <div className={cn(
          'flex items-center justify-between gap-2 px-3.5 pt-3.5 pb-1',
          collapsed && 'flex-col justify-center gap-1.5 px-1.5'
        )}>
          <div className={cn('flex items-center gap-2.5 overflow-hidden', collapsed && 'justify-center')}>
            <div className="h-[26px] w-[26px] rounded-[7px] bg-accent-gradient text-white font-semibold text-xs grid place-items-center shrink-0 shadow-ring">
              S
            </div>
            {!collapsed && <span className="text-sm font-semibold tracking-tight">SMART_bot</span>}
          </div>
          <button
            onClick={() => setCollapsed(!collapsed)}
            aria-label={collapsed ? 'Mở rộng' : 'Thu gọn'}
            className="h-[26px] w-[26px] rounded-md grid place-items-center text-[hsl(var(--dim))] hover:text-foreground hover:bg-[hsl(var(--hover))] transition-colors"
          >
            <ChevronLeft className={cn('h-3.5 w-3.5 transition-transform', collapsed && 'rotate-180')} />
          </button>
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
                    <Icon className={cn('h-[15px] w-[15px] shrink-0', active && 'text-[hsl(var(--primary))]')} strokeWidth={1.8} />
                    {!collapsed && <span className="truncate">{item.label}</span>}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <UserMenu me={me} collapsed={collapsed} />
      </motion.aside>

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
            <Button
              variant="outline"
              size="sm"
              className="h-[30px] gap-2"
              onClick={() => setPaletteOpen(true)}
              aria-label="Tìm kiếm"
            >
              <Search className="h-3.5 w-3.5" />
              <span className="max-sm:hidden text-[11px]">Tìm kiếm</span>
              <Kbd className="max-sm:hidden">⌘K</Kbd>
            </Button>
            <ThemeToggle />
          </div>
        </div>

        {children}
      </main>

      <CommandPalette nav={nav} />
    </div>
  );
}
```

- [ ] **Step 2: Run dev — verify**

```bash
cd frontend && pnpm dev
```
In another shell, open `http://localhost:5173/app/admin/dashboard` (after logging in). Verify: `⌘K` opens palette, clicking a nav item navigates and closes, mobile breakpoint shows menu icon.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/app-shell.tsx
git commit -m "feat(app-shell): wire ⌘K palette + spring mobile drawer"
```

---

## Task 8: Dashboard sub-components

**Files:**
- Create: `frontend/src/modules/admin/features/dashboard/components/stat-card.tsx`
- Create: `frontend/src/modules/admin/features/dashboard/components/recent-groups.tsx`
- Create: `frontend/src/modules/admin/features/dashboard/components/today-items.tsx`
- Create: `frontend/src/modules/admin/features/dashboard/components/activity-feed.tsx`
- Create: `frontend/src/modules/admin/features/dashboard/components/dashboard-skeleton.tsx`

- [ ] **Step 1: Write `stat-card.tsx`**

```tsx
import { useEffect, useState } from 'react';
import { motion, useMotionValue, animate, useReducedMotion } from 'framer-motion';
import { Card } from '@/components/ui/card';
import { ease, fadeUp } from '@/lib/motion';
import { cn } from '@/lib/utils';

type Props = { label: string; value: number; previous: number };

function formatDelta(current: number, previous: number): { text: string; tone: 'up' | 'down' | 'flat' | 'new' } {
  if (previous === 0 && current === 0) return { text: '→ 0%', tone: 'flat' };
  if (previous === 0) return { text: 'Mới', tone: 'new' };
  const pct = Math.round(((current - previous) / previous) * 100);
  if (pct > 0) return { text: `↗ +${pct}%`, tone: 'up' };
  if (pct < 0) return { text: `↘ ${pct}%`, tone: 'down' };
  return { text: '→ 0%', tone: 'flat' };
}

export function StatCard({ label, value, previous }: Props) {
  const reduce = useReducedMotion();
  const mv = useMotionValue(reduce ? value : 0);
  const [display, setDisplay] = useState(reduce ? value : 0);
  const delta = formatDelta(value, previous);

  useEffect(() => {
    if (reduce) {
      setDisplay(value);
      return;
    }
    const controls = animate(mv, value, {
      duration: 1.0,
      ease,
      onUpdate: (v) => setDisplay(Math.round(v)),
    });
    return () => controls.stop();
  }, [value, reduce, mv]);

  return (
    <motion.div variants={fadeUp}>
      <Card variant="glow" className="px-4 py-3.5 relative">
        <div className="absolute left-0 right-0 top-0 h-px bg-accent-gradient opacity-50" />
        <div className="text-[10px] uppercase tracking-wider text-[hsl(var(--dim))] font-medium">{label}</div>
        <div className="text-[22px] font-semibold tracking-tight mt-1 tabular-nums">
          {display.toLocaleString('vi-VN')}
        </div>
        <div
          className={cn(
            'text-[10px] mt-0.5 tabular-nums font-medium',
            delta.tone === 'up' && 'text-[hsl(var(--ok))]',
            delta.tone === 'down' && 'text-[hsl(var(--danger))]',
            delta.tone === 'flat' && 'text-[hsl(var(--dim))]',
            delta.tone === 'new' && 'text-[hsl(var(--primary))]'
          )}
        >
          {delta.text} <span className="text-[hsl(var(--dim))] font-normal">vs 30d trước</span>
        </div>
      </Card>
    </motion.div>
  );
}
```

- [ ] **Step 2: Write `recent-groups.tsx`**

```tsx
import { motion } from 'framer-motion';
import { Users } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { fadeUp } from '@/lib/motion';

type Group = {
  id: number;
  name: string;
  provider: string;
  msg_count_7d: number;
  updated_at: string;
};

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s trước`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}p trước`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h trước`;
  const d = Math.floor(h / 24);
  return `${d}d trước`;
}

export function RecentGroups({ groups }: { groups: Group[] }) {
  return (
    <motion.div variants={fadeUp}>
      <Card>
        <CardHeader>
          <CardTitle>Nhóm gần đây</CardTitle>
          <span className="text-[10px] text-[hsl(var(--dim))]">{groups.length} nhóm</span>
        </CardHeader>
        <CardBody>
          {groups.length === 0 ? (
            <div className="flex flex-col items-center py-8 gap-2">
              <Users className="h-7 w-7 text-muted-foreground/30" />
              <p className="text-[12px] text-muted-foreground">Chưa có nhóm nào</p>
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {groups.map((g) => (
                <li
                  key={g.id}
                  className="py-2 flex items-center justify-between gap-2 transition-transform hover:translate-x-[2px]"
                >
                  <div className="min-w-0">
                    <div className="text-[12.5px] font-medium truncate">{g.name}</div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">
                      {relativeTime(g.updated_at)}
                    </div>
                  </div>
                  <Badge variant="secondary">{g.provider}</Badge>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </motion.div>
  );
}
```

- [ ] **Step 3: Write `today-items.tsx`**

```tsx
import { motion } from 'framer-motion';
import { ClipboardList } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/card';
import { fadeUp } from '@/lib/motion';

type Item = {
  id: number;
  text: string;
  due_at: string | null;
  status: string;
  assignee_name: string | null;
  group_name: string;
};

export function TodayItems({ items }: { items: Item[] }) {
  return (
    <motion.div variants={fadeUp}>
      <Card>
        <CardHeader>
          <CardTitle>Việc cần làm hôm nay</CardTitle>
          <span className="text-[10px] text-[hsl(var(--dim))]">{items.length} việc</span>
        </CardHeader>
        <CardBody>
          {items.length === 0 ? (
            <div className="flex flex-col items-center py-8 gap-2">
              <ClipboardList className="h-7 w-7 text-muted-foreground/30" />
              <p className="text-[12px] text-muted-foreground">Hôm nay rảnh, nghỉ thôi.</p>
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {items.map((it) => (
                <li
                  key={it.id}
                  className="py-2 flex items-start justify-between gap-2 transition-transform hover:translate-x-[2px]"
                >
                  <div className="min-w-0">
                    <div className="text-[12.5px] truncate">{it.text}</div>
                    <div className="text-[10px] text-muted-foreground mt-0.5 truncate">
                      {it.group_name}
                      {it.assignee_name && ` · ${it.assignee_name}`}
                    </div>
                  </div>
                  {it.due_at && (
                    <span className="text-[10px] text-muted-foreground shrink-0 mt-0.5 tabular-nums">
                      {new Date(it.due_at).toLocaleTimeString('vi-VN', {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </motion.div>
  );
}
```

- [ ] **Step 4: Write `activity-feed.tsx`**

```tsx
import { motion } from 'framer-motion';
import { BarChart2 } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { fadeUp } from '@/lib/motion';

type Activity = { kind: string; id: number; title: string; status: string; ts: string };

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s trước`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}p trước`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h trước`;
  const d = Math.floor(h / 24);
  return `${d}d trước`;
}

function kindLabel(kind: string): string {
  if (kind === 'action_item') return 'việc';
  if (kind === 'reminder') return 'nhắc';
  return kind;
}

export function ActivityFeed({ items }: { items: Activity[] }) {
  return (
    <motion.div variants={fadeUp}>
      <Card>
        <CardHeader>
          <CardTitle>Hoạt động gần đây</CardTitle>
          <Badge variant="live">Realtime</Badge>
        </CardHeader>
        <CardBody>
          {items.length === 0 ? (
            <div className="flex flex-col items-center py-8 gap-2">
              <BarChart2 className="h-7 w-7 text-muted-foreground/30" />
              <p className="text-[12px] text-muted-foreground">Chưa có hoạt động nào</p>
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {items.map((a, i) => (
                <li
                  key={`${a.kind}-${a.id}-${i}`}
                  className="py-2 flex items-center gap-3 transition-transform hover:translate-x-[2px]"
                >
                  <Badge variant="secondary">{kindLabel(a.kind)}</Badge>
                  <span className="text-[12.5px] truncate flex-1">{a.title}</span>
                  <span className="text-[10px] text-muted-foreground shrink-0 tabular-nums">
                    {relativeTime(a.ts)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </motion.div>
  );
}
```

- [ ] **Step 5: Write `dashboard-skeleton.tsx`**

```tsx
import { Skeleton } from '@/components/ui/skeleton';

export function DashboardSkeleton() {
  return (
    <div className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1140px] space-y-5">
      <div className="space-y-2">
        <Skeleton className="h-7 w-72" />
        <Skeleton className="h-3.5 w-56" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[78px] rounded-[12px]" />)}
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <Skeleton className="h-[240px] rounded-[12px]" />
        <Skeleton className="h-[240px] rounded-[12px]" />
      </div>
      <Skeleton className="h-[200px] rounded-[12px]" />
    </div>
  );
}
```

- [ ] **Step 6: Typecheck**

```bash
pnpm typecheck
```
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/modules/admin/features/dashboard/components/
git commit -m "feat(dashboard): stat-card, groups, today-items, activity-feed, skeleton"
```

---

## Task 9: Rewrite `dashboard/page.tsx`

**Files:**
- Modify: `frontend/src/modules/admin/features/dashboard/page.tsx`

- [ ] **Step 1: Replace file contents**

```tsx
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { staggerContainer, fadeUp } from '@/lib/motion';
import { StatCard } from './components/stat-card';
import { RecentGroups } from './components/recent-groups';
import { TodayItems } from './components/today-items';
import { ActivityFeed } from './components/activity-feed';
import { DashboardSkeleton } from './components/dashboard-skeleton';

type DashboardData = {
  recent_groups: Array<{ id: number; name: string; provider: string; msg_count_7d: number; updated_at: string }>;
  today_items: Array<{ id: number; text: string; due_at: string | null; status: string; assignee_name: string | null; group_name: string }>;
  stats_30d: { messages: number; tasks: number; reminders: number; decisions: number };
  stats_prev_30d: { messages: number; tasks: number; reminders: number; decisions: number };
  recent_activity: Array<{ kind: string; id: number; title: string; status: string; ts: string }>;
};

function greet(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Chào buổi sáng';
  if (h < 18) return 'Chào buổi chiều';
  return 'Chào buổi tối';
}

export default function DashboardPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['admin', 'dashboard'],
    queryFn: () => api<DashboardData>('/api/v1/admin/dashboard'),
    staleTime: 30_000,
  });

  if (isLoading) return <DashboardSkeleton />;

  if (isError || !data) {
    return (
      <div className="px-10 py-8 max-md:px-4">
        <div className="rounded-[12px] border border-border bg-card px-5 py-6 max-w-md">
          <p className="text-[12.5px] font-medium text-foreground">Không tải được dashboard</p>
          <p className="text-[11px] text-muted-foreground mt-1">Có thể do mạng hoặc phiên đăng nhập. Thử lại?</p>
          <Button size="sm" className="mt-3" onClick={() => refetch()}>Thử lại</Button>
        </div>
      </div>
    );
  }

  return (
    <motion.div
      className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1140px] space-y-5"
      variants={staggerContainer(0.08)}
      initial="hidden"
      animate="show"
    >
      <motion.header variants={fadeUp}>
        <h1 className="text-[26px] font-semibold tracking-tight leading-tight">
          {greet()}, <span className="text-accent-gradient">boss.</span>
        </h1>
        <p className="text-muted-foreground mt-1 text-[12.5px]">
          Tổng quan workspace · 30 ngày qua
        </p>
      </motion.header>

      <motion.div
        className="grid grid-cols-2 md:grid-cols-4 gap-3"
        variants={staggerContainer(0.06)}
      >
        <StatCard label="Tin nhắn" value={data.stats_30d.messages} previous={data.stats_prev_30d.messages} />
        <StatCard label="Việc cần làm" value={data.stats_30d.tasks} previous={data.stats_prev_30d.tasks} />
        <StatCard label="Nhắc nhở" value={data.stats_30d.reminders} previous={data.stats_prev_30d.reminders} />
        <StatCard label="Quyết định" value={data.stats_30d.decisions} previous={data.stats_prev_30d.decisions} />
      </motion.div>

      <motion.div className="grid md:grid-cols-2 gap-3" variants={staggerContainer(0.08)}>
        <RecentGroups groups={data.recent_groups} />
        <TodayItems items={data.today_items} />
      </motion.div>

      <ActivityFeed items={data.recent_activity} />
    </motion.div>
  );
}
```

- [ ] **Step 2: Run dev — verify in browser**

```bash
cd frontend && pnpm dev
```
Open `http://localhost:5173/app/admin/dashboard` (logged in as `boss@local.test` / `boss123`). Verify:
- Greeting renders with gradient "boss."
- 4 stat cards count up from 0
- Delta % shows correct tone (or "Mới" / "→ 0%")
- Groups + today items render or show empty state
- Activity feed shows "Realtime" pulse badge
- Entrance stagger is visible on first load

- [ ] **Step 3: Commit**

```bash
git add frontend/src/modules/admin/features/dashboard/page.tsx
git commit -m "feat(dashboard): rewrite page with stagger, count-up, delta, refined cards"
```

---

## Task 10: AdminLayout page transition

**Files:**
- Modify: `frontend/src/modules/admin/layout.tsx`

- [ ] **Step 1: Patch**

Replace file with:

```tsx
import { Outlet, useLoaderData, useLocation, useMatches } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { AppShell } from '@/components/app-shell';
import { pageTransition } from '@/lib/motion';
import type { Me } from '@/lib/auth';
import { adminNav } from './nav';

export default function AdminLayout() {
  const me = useLoaderData() as Me;
  const matches = useMatches();
  const location = useLocation();
  const crumbs = matches
    .filter((m) => m.handle && (m.handle as any).breadcrumb)
    .map((m) => (m.handle as any).breadcrumb);
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
      <AnimatePresence mode="wait">
        <motion.div
          key={location.pathname}
          initial={pageTransition.initial}
          animate={pageTransition.animate}
          exit={pageTransition.exit}
        >
          <Outlet />
        </motion.div>
      </AnimatePresence>
    </AppShell>
  );
}
```

- [ ] **Step 2: Verify in dev**

Switch between `/app/admin/dashboard` → `/app/admin/groups` → back. Confirm a 250 ms fade+slide on each navigation.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/modules/admin/layout.tsx
git commit -m "feat(admin-layout): wrap Outlet with AnimatePresence page transition"
```

---

## Task 11: E2E smoke — dashboard renders + ⌘K opens

**Files:**
- Modify: `frontend/tests/admin-flow.spec.ts`

- [ ] **Step 1: Add tests**

Inside the `test.describe('Admin (boss) flow', ...)` block (after the existing `'dashboard — greeting + stat cards'` test), add:

```ts
  test('dashboard — 4 stat cards with delta', async ({ page }) => {
    await page.goto('/app/admin/dashboard');
    await expect(page.getByText('Tin nhắn').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Việc cần làm').first()).toBeVisible();
    await expect(page.getByText('Nhắc nhở').first()).toBeVisible();
    await expect(page.getByText('Quyết định').first()).toBeVisible();
    // Delta line is rendered for each (either "Mới", "→ 0%", or "↗/↘ N%")
    await expect(page.getByText(/Mới|→ 0%|↗|↘/).first()).toBeVisible();
  });

  test('⌘K opens command palette', async ({ page }) => {
    await page.goto('/app/admin/dashboard');
    await page.keyboard.press('Meta+K');
    await expect(page.getByPlaceholder(/Tìm trang/i)).toBeVisible({ timeout: 5000 });
    await page.keyboard.press('Escape');
    await expect(page.getByPlaceholder(/Tìm trang/i)).toBeHidden();
  });
```

- [ ] **Step 2: Run (only if `E2E_BOSS_COOKIE` is set, else skipped — OK)**

```bash
cd frontend && pnpm e2e --grep "Admin"
```
Expected: tests pass if cookie env is set, else skipped (test guard at top of file already handles this).

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/admin-flow.spec.ts
git commit -m "test(e2e): dashboard delta line + ⌘K palette open"
```

---

## Task 12: Final manual verification

- [ ] **Step 1: Run typecheck + build**

```bash
cd frontend && pnpm typecheck && pnpm build
```
Expected: both pass.

- [ ] **Step 2: Run backend tests**

```bash
cd .. && pytest tests/integration/test_api_admin_dashboard.py -v
```
Expected: all pass.

- [ ] **Step 3: Manual visual check**

```bash
./scripts/restart.sh
```
Open `http://0.0.0.0:8000/app/admin/dashboard`, log in as `boss@local.test` / `boss123`.

Verify checklist:
- [ ] Greeting + accent-gradient "boss." visible
- [ ] 4 stat cards count up from 0 on first paint
- [ ] Delta % renders with correct tone (green up / rose down / `Mới` if prev = 0)
- [ ] Groups + Today items + Activity feed each appear with stagger
- [ ] ⌘K (or Ctrl+K) opens palette; nav items + "Đổi chế độ sáng/tối" + "Đăng xuất" work
- [ ] Theme toggle in topbar still works; dashboard re-renders cleanly in light
- [ ] Resize to ~375px width: stats become 2×2, drawer opens via menu icon with spring
- [ ] Navigate to another admin page → return → page transition fade+slide visible
- [ ] No console errors

- [ ] **Step 4: Commit any final polish**

If anything required a fix, commit it with a `polish(dashboard): <what>` message. Otherwise this task ends here.

---

## Out of Scope (Reminder)

- Other admin pages (action-items, groups, reminders, settings, …)
- Superadmin pages
- Public landing / signup
- Sparkline per stat card
- Server-side global search in ⌘K
