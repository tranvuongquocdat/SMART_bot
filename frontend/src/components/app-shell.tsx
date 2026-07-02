import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronLeft, Menu, Search, type LucideIcon } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { Kbd } from '@/components/ui/kbd';
import { ThemeToggle } from './theme-toggle';
import { UserMenu } from './user-menu';
import { NotificationBell } from './notification-bell';
import { LanguageToggle } from './language-toggle';
import { CommandPalette } from './command-palette';
import type { Me } from '@/lib/auth';
import { cn } from '@/lib/utils';
import { spring } from '@/lib/motion';
import { useT } from '@/lib/i18n';

export type NavItem = { label: string; href: string; icon: LucideIcon };
export type NavSection = { label: string; items: NavItem[] };
// badges: đếm việc chờ theo href (vd request gói pending) — hiện pill cạnh label.
export type NavBadges = Record<string, number | undefined>;

export function AppShell({
  nav,
  me,
  breadcrumb,
  children,
  badges,
}: {
  nav: NavSection[];
  me: Me;
  breadcrumb: ReactNode;
  children: ReactNode;
  badges?: NavBadges;
}) {
  const t = useT();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(
    typeof window !== 'undefined' ? window.innerWidth < 768 : false,
  );
  const location = useLocation();
  const sb = collapsed ? '60px' : '232px';

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

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
          'flex flex-col border-r border-[hsl(var(--divider))] bg-[hsl(var(--sidebar))] relative z-30',
          'md:sticky md:top-0 md:h-screen md:translate-x-0 md:w-auto md:min-w-0',
          'fixed inset-y-0 left-0 w-[260px]',
        )}
        animate={{ x: isMobile && !mobileOpen ? -260 : 0 }}
        transition={spring}
      >
        <div
          className={cn(
            'flex items-center justify-between gap-2 px-3.5 pt-3.5 pb-1',
            collapsed && 'flex-col justify-center gap-1.5 px-1.5',
          )}
        >
          <div className={cn('flex items-center gap-2.5 overflow-hidden', collapsed && 'justify-center')}>
            <div className="h-[26px] w-[26px] rounded-[7px] bg-accent-gradient text-white font-semibold text-xs grid place-items-center shrink-0 shadow-ring">
              S
            </div>
            {!collapsed && <span className="text-sm font-semibold tracking-tight">SMART_bot</span>}
          </div>
          <button
            onClick={() => setCollapsed(!collapsed)}
            aria-label={collapsed ? t('common.expand') : t('common.collapse')}
            className="h-[26px] w-[26px] rounded-md grid place-items-center text-[hsl(var(--dim))] hover:text-foreground hover:bg-[hsl(var(--hover))] transition-colors"
          >
            <ChevronLeft className={cn('h-3.5 w-3.5 transition-transform', collapsed && 'rotate-180')} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-2.5 py-2">
          {nav.map((section) => (
            <div key={section.label}>
              {!collapsed && (
                <div className="text-[10px] uppercase tracking-wider text-[hsl(var(--dim))] px-2.5 pt-4 pb-1.5 font-medium">
                  {t(section.label)}
                </div>
              )}
              {section.items.map((item) => {
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
                      collapsed && 'justify-center px-2.5',
                    )}
                  >
                    <Icon
                      className={cn('h-[15px] w-[15px] shrink-0', active && 'text-[hsl(var(--primary))]')}
                      strokeWidth={1.8}
                    />
                    {!collapsed && <span className="truncate">{t(item.label)}</span>}
                    {!collapsed && (badges?.[item.href] ?? 0) > 0 && (
                      <span className="ml-auto shrink-0 rounded-full bg-[hsl(var(--primary))] px-1.5 py-px text-[10px] font-semibold leading-4 text-primary-foreground tabular-nums">
                        {badges![item.href]}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
      </motion.aside>

      <main>
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-[hsl(var(--divider))] bg-[hsl(var(--topbar)/0.85)] backdrop-blur px-7 py-3.5 max-md:px-4">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() => setMobileOpen(true)}
              className="md:hidden h-[30px] w-[30px] rounded-md border border-[hsl(var(--divider))] grid place-items-center"
              aria-label={t('common.openMenu')}
            >
              <Menu className="h-4 w-4" />
            </button>
            <div className="text-[13px] text-muted-foreground truncate">{breadcrumb}</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              aria-label={t('common.search')}
              className="h-[30px] px-[10px] rounded-[7px] bg-transparent text-[hsl(var(--muted-foreground))] flex items-center gap-2 text-[11px] surface-section hover:bg-[hsl(var(--hover))] transition-colors"
            >
              <Search className="h-3.5 w-3.5" />
              <span className="max-sm:hidden">{t('common.search')}</span>
              <Kbd className="max-sm:hidden">⌘K</Kbd>
            </button>
            <LanguageToggle />
            <ThemeToggle />
            <NotificationBell />
            <UserMenu me={me} placement="topbar" />
          </div>
        </div>

        {children}
      </main>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} nav={nav} />
    </div>
  );
}
