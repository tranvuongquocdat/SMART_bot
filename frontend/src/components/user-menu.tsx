import { ChevronDown, LogOut, Settings, User } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { Me } from '@/lib/auth';

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
          onClick={handleLogout}
        >
          <LogOut className="mr-2 h-4 w-4" />Đăng xuất
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
