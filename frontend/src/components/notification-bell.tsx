import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Bell, CreditCard, Megaphone, Info } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { relativeTime } from '@/lib/format';
import { useT } from '@/lib/i18n';
import {
  notificationsQuery,
  markNotificationsRead,
  type Notification,
} from '@/lib/notifications';

const KIND_ICON = {
  subscription: CreditCard,
  announcement: Megaphone,
  system: Info,
} as const;

export function NotificationBell() {
  const t = useT();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data } = useQuery(notificationsQuery);
  const items = data?.items ?? [];
  const unread = data?.unread_count ?? 0;

  const invalidate = () => qc.invalidateQueries({ queryKey: ['me', 'notifications'] });

  const markOne = useMutation({
    mutationFn: (id: number) => markNotificationsRead(id),
    onSuccess: invalidate,
  });
  const markAll = useMutation({
    mutationFn: () => markNotificationsRead(),
    onSuccess: invalidate,
  });

  function openItem(n: Notification) {
    if (!n.is_read) markOne.mutate(n.id);
    if (n.link) navigate(n.link);
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="relative h-[30px] w-[30px] rounded-[7px] grid place-items-center text-[hsl(var(--muted-foreground))] surface-section hover:bg-[hsl(var(--hover))] hover:text-foreground transition-colors"
          aria-label={t('notif.title')}
        >
          <Bell className="h-4 w-4" />
          {unread > 0 && (
            <span className="absolute -top-1 -right-1 min-w-[16px] h-[16px] px-1 rounded-full bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] text-[10px] font-semibold grid place-items-center tabular-nums">
              {unread > 9 ? '9+' : unread}
            </span>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between px-3 py-2 border-b border-[hsl(var(--divider))]">
          <span className="text-sm font-medium">{t('notif.title')}</span>
          {unread > 0 && (
            <button
              className="text-[11px] text-[hsl(var(--primary))] hover:underline"
              onClick={(e) => {
                e.preventDefault();
                markAll.mutate();
              }}
            >
              {t('notif.markRead')}
            </button>
          )}
        </div>

        <div className="max-h-[360px] overflow-y-auto">
          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              {t('notif.empty')}
            </p>
          ) : (
            items.map((n) => {
              const Icon = KIND_ICON[n.kind] ?? Info;
              return (
                <button
                  key={n.id}
                  onClick={() => openItem(n)}
                  className={`w-full text-left flex gap-2.5 px-3 py-2.5 border-b border-[hsl(var(--divider))] last:border-0 transition-colors hover:bg-[hsl(var(--hover))] ${
                    n.is_read ? '' : 'bg-[hsl(var(--primary-soft))]'
                  }`}
                >
                  <Icon className="h-4 w-4 mt-0.5 shrink-0 text-[hsl(var(--primary))]" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-[13px] font-medium truncate flex-1">{n.title}</p>
                      {!n.is_read && (
                        <span className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--primary))] shrink-0" />
                      )}
                    </div>
                    {n.body && (
                      <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">{n.body}</p>
                    )}
                    <p className="text-[11px] text-[hsl(var(--dim))] mt-0.5">
                      {relativeTime(n.created_at)}
                    </p>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
