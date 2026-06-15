import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useI18n } from '@/lib/i18n';
import type { TimelineMsg } from './api';

export function TimelineCard({ messages }: { messages: TimelineMsg[] }) {
  const { t, lang } = useI18n();
  const locale = lang === 'en' ? 'en-US' : 'vi-VN';
  if (messages.length === 0) {
    return <p className="text-sm text-muted-foreground py-8 text-center">{t('grp.empty.timeline')}</p>;
  }
  const groups = groupByDate(messages, locale);
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
                    {new Date(m.created_at).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
                <p className="text-[13.5px] leading-[1.55]">{m.text}</p>
                {m.extracted && (
                  <span className="mt-2 inline-flex items-center gap-1.5 text-[11.5px] text-primary px-2 py-[3px] bg-[hsl(var(--primary-soft))] rounded cursor-pointer">
                    <Check className="h-2.5 w-2.5" />
                    {t('grp.extracted', { what: m.extracted })}
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

function groupByDate(msgs: TimelineMsg[], locale: string): [string, TimelineMsg[]][] {
  const map = new Map<string, TimelineMsg[]>();
  for (const m of msgs) {
    const key = new Date(m.created_at).toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'numeric' });
    map.set(key, [...(map.get(key) ?? []), m]);
  }
  return Array.from(map.entries());
}
