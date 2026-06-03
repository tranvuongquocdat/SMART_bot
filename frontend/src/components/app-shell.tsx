import { useState } from 'react';
import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronLeft, Menu, Search, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from './theme-toggle';
import { UserMenu } from './user-menu';
import type { Me } from '@/lib/auth';
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
            className="absolute -right-3 top-4 h-6 w-6 rounded-full bg-card border border-[hsl(var(--border-strong))] grid place-items-center text-[hsl(var(--dim))] hover:text-foreground"
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
