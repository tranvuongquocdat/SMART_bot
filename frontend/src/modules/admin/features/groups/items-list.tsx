import { User, Calendar } from 'lucide-react';
import { relativeTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useI18n } from '@/lib/i18n';
import type { Item } from './api';

const TAG_STYLE: Record<Item['type'], { labelKey: string; cls: string }> = {
  task: { labelKey: 'grp.itemType.task', cls: 'text-[hsl(var(--info))] bg-[hsl(var(--info)/0.1)]' },
  reminder: { labelKey: 'grp.itemType.reminder', cls: 'text-[hsl(var(--warn))] bg-[hsl(var(--warn)/0.1)]' },
  decision: { labelKey: 'grp.itemType.decision', cls: 'text-primary bg-[hsl(var(--primary)/0.1)]' },
};

export function ItemsList({ items }: { items: Item[] }) {
  const { t, lang } = useI18n();
  const locale = lang === 'en' ? 'en-US' : 'vi-VN';
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground py-8 text-center">{t('grp.empty.itemsToday')}</p>;
  }
  return (
    <div className="flex flex-col gap-1.5">
      {items.map(it => {
        const tag = TAG_STYLE[it.type];
        return (
          <div key={`${it.type}-${it.id}`} className="flex items-start gap-2.5 py-2.5 px-3.5 bg-card rounded-lg shadow-[0_0_0_1px_hsl(var(--border-strong)),0_1px_2px_rgba(0,0,0,.04)] hover:bg-[hsl(var(--hover))] transition-colors cursor-pointer">
            <div className="h-4 w-4 rounded border-[1.5px] border-[hsl(var(--border-strong))] mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-[13.5px] tracking-tight mb-1">{it.text}</p>
              <div className="text-xs text-muted-foreground flex items-center gap-2.5 flex-wrap">
                <span className={cn('text-[10.5px] py-px px-1.5 rounded font-medium uppercase tracking-wide', tag.cls)}>{t(tag.labelKey)}</span>
                {it.assignee && (
                  <span className="inline-flex items-center gap-1"><User className="h-3 w-3" />{it.assignee}</span>
                )}
                {it.due_at && (
                  <span className="inline-flex items-center gap-1"><Calendar className="h-3 w-3" />{relativeTime(it.due_at)}</span>
                )}
              </div>
            </div>
            <span className="text-[11px] text-[hsl(var(--dim))] shrink-0 mt-0.5">{new Date(it.created_at).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        );
      })}
    </div>
  );
}
