import { ChevronDown, LogOut, Settings, CreditCard } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { Me } from '@/lib/auth';
import { useT } from '@/lib/i18n';

function readCsrfCookie(): string {
  const m = document.cookie.match(/(?:^|;\s*)smart_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

function handleLogout() {
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = '/logout';
  const csrf = document.createElement('input');
  csrf.type = 'hidden';
  csrf.name = '_csrf';
  csrf.value = readCsrfCookie();
  form.appendChild(csrf);
  document.body.appendChild(form);
  form.submit();
}

export function UserMenu({
  me,
  collapsed = false,
  placement = 'sidebar',
}: {
  me: Me;
  collapsed?: boolean;
  placement?: 'sidebar' | 'topbar';
}) {
  const t = useT();
  const navigate = useNavigate();
  const initials = (String(me.id)[0] || 'U').toUpperCase();
  const roleLabel = me.roles.includes('superadmin') ? t('usermenu.roleSuperadmin') : t('usermenu.roleOwner');

  const trigger =
    placement === 'topbar' ? (
      <button
        className="h-[30px] w-[30px] rounded-full bg-gradient-to-br from-[hsl(168_70%_45%)] to-[hsl(200_65%_45%)] text-white text-[11px] font-semibold grid place-items-center shrink-0 ring-1 ring-[hsl(var(--border-strong))] hover:opacity-90 transition-opacity"
        aria-label={t('common.account')}
      >
        {initials}
      </button>
    ) : (
      <button className="flex items-center gap-2.5 w-full px-3 py-2.5 border-t border-[hsl(var(--divider))] hover:bg-[hsl(var(--hover))] transition-colors">
        <div className="h-7 w-7 rounded-full bg-gradient-to-br from-[hsl(168_70%_45%)] to-[hsl(200_65%_45%)] text-white text-[11px] font-semibold grid place-items-center shrink-0">
          {initials}
        </div>
        {!collapsed && (
          <>
            <div className="flex-1 text-left min-w-0">
              <div className="text-[12.5px] font-medium truncate">User #{me.id}</div>
              <div className="text-[11px] text-[hsl(var(--dim))]">{roleLabel}</div>
            </div>
            <ChevronDown className="h-3.5 w-3.5 text-[hsl(var(--dim))]" />
          </>
        )}
      </button>
    );

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
      <DropdownMenuContent
        side={placement === 'topbar' ? 'bottom' : 'top'}
        align="end"
        className="w-56"
      >
        {placement === 'topbar' && (
          <>
            <div className="px-2 py-1.5">
              <div className="text-[12.5px] font-medium truncate">User #{me.id}</div>
              <div className="text-[11px] text-[hsl(var(--dim))]">{roleLabel}</div>
            </div>
            <DropdownMenuSeparator />
          </>
        )}
        <DropdownMenuItem onClick={() => navigate('/app/admin/subscription')}>
          <CreditCard className="mr-2 h-4 w-4" />{t('usermenu.subscription')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => navigate('/app/admin/settings')}>
          <Settings className="mr-2 h-4 w-4" />{t('nav.admin.settings')}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="text-destructive focus:text-destructive"
          onClick={handleLogout}
        >
          <LogOut className="mr-2 h-4 w-4" />{t('usermenu.logout')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
