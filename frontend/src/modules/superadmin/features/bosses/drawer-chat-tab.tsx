import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MessageSquare, Users } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useI18n, type Lang } from '@/lib/i18n';
import {
  bossConversationsQuery,
  bossMessages,
  type BossChatMessage,
  type BossConversation,
} from './api';

function providerBadge(provider: string) {
  if (provider === 'zalo') return <Badge variant="zalo">zalo</Badge>;
  if (provider === 'telegram') return <Badge variant="telegram">telegram</Badge>;
  return <Badge variant="secondary">{provider}</Badge>;
}

function dayLabel(ts: string, t: (k: string) => string, lang: Lang): string {
  const d = new Date(ts);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const same = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();
  if (same(d, today)) return t('sa.boss.chatToday');
  if (same(d, yesterday)) return t('sa.boss.chatYesterday');
  return d.toLocaleDateString(lang === 'en' ? 'en-US' : 'vi-VN', {
    weekday: 'long',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

function MessageList({
  bossId,
  conv,
}: {
  bossId: number;
  conv: BossConversation;
}) {
  const { t, lang } = useI18n();
  const locale = lang === 'en' ? 'en-US' : 'vi-VN';
  const [messages, setMessages] = useState<BossChatMessage[]>([]);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchPage = async (before: string | null, replace: boolean) => {
    setLoading(true);
    try {
      const res = await bossMessages(bossId, conv.provider, conv.chat_id, before);
      setMessages((prev) => (replace ? res.messages : [...res.messages, ...prev]));
      setNextBefore(res.next_before);
    } catch {
      toast.error(t('sa.boss.chatLoadError'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setMessages([]);
    setNextBefore(null);
    fetchPage(null, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bossId, conv.provider, conv.chat_id]);

  if (loading && messages.length === 0) return <Skeleton className="h-60 w-full" />;
  if (messages.length === 0)
    return <p className="text-sm text-muted-foreground p-4">{t('sa.boss.chatEmpty')}</p>;

  // Chèn separator theo ngày
  const rows: ({ kind: 'day'; label: string; key: string } | { kind: 'msg'; m: BossChatMessage })[] =
    [];
  let lastDay = '';
  for (const m of messages) {
    const day = m.ts.slice(0, 10);
    if (day !== lastDay) {
      rows.push({ kind: 'day', label: dayLabel(m.ts, t, lang), key: `day-${day}` });
      lastDay = day;
    }
    rows.push({ kind: 'msg', m });
  }

  return (
    <div className="space-y-2 p-1">
      {nextBefore && (
        <div className="text-center">
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            disabled={loading}
            onClick={() => fetchPage(nextBefore, false)}
          >
            {loading ? t('sa.common.loading') : t('sa.boss.loadOlder')}
          </Button>
        </div>
      )}
      {rows.map((row) =>
        row.kind === 'day' ? (
          <div key={row.key} className="flex items-center gap-3 py-1">
            <div className="h-px flex-1 bg-border" />
            <span className="text-[11px] text-muted-foreground whitespace-nowrap">
              {row.label}
            </span>
            <div className="h-px flex-1 bg-border" />
          </div>
        ) : (
          <div
            key={`${row.m.direction}-${row.m.id}`}
            className={`flex ${row.m.direction === 'out' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap break-words ${
                row.m.direction === 'out'
                  ? 'bg-primary/10 border border-primary/20'
                  : 'bg-card border'
              }`}
            >
              <p className="text-[11px] font-medium text-muted-foreground mb-0.5">
                {row.m.direction === 'out' ? t('sa.boss.bot') : row.m.sender_name ?? t('sa.boss.unknown')}
                <span className="font-normal ml-2">
                  {new Date(row.m.ts).toLocaleTimeString(locale, {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
              </p>
              {row.m.text && <p>{row.m.text}</p>}
              {row.m.media_kind && row.m.media_kind !== 'text' && (
                <p className="text-xs text-muted-foreground italic mt-0.5">
                  [{row.m.media_kind}]
                </p>
              )}
            </div>
          </div>
        )
      )}
    </div>
  );
}

export function BossChatTab({ bossId }: { bossId: number }) {
  const { t, lang } = useI18n();
  const locale = lang === 'en' ? 'en-US' : 'vi-VN';
  const convs = useQuery(bossConversationsQuery(bossId));
  const [selected, setSelected] = useState<BossConversation | null>(null);

  useEffect(() => {
    if (!selected && convs.data && convs.data.length > 0) setSelected(convs.data[0]);
  }, [convs.data, selected]);

  if (convs.isLoading) return <Skeleton className="h-60 w-full" />;
  if (!convs.data || convs.data.length === 0)
    return (
      <p className="text-sm text-muted-foreground">
        {t('sa.boss.noConversations')}
      </p>
    );

  return (
    <div className="flex gap-0 -m-5 h-[calc(100%+2.5rem)] min-h-0">
      {/* Danh sách hội thoại */}
      <div className="w-60 shrink-0 border-r overflow-y-auto">
        {convs.data.map((c) => {
          const active =
            selected?.provider === c.provider && selected?.chat_id === c.chat_id;
          return (
            <button
              key={`${c.provider}:${c.chat_id}`}
              onClick={() => setSelected(c)}
              className={`w-full text-left px-3 py-2.5 border-b transition-colors ${
                active ? 'bg-[hsl(var(--hover))]' : 'hover:bg-[hsl(var(--hover))]'
              }`}
            >
              <div className="flex items-center gap-1.5 min-w-0">
                {c.chat_type === 'group' ? (
                  <Users className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                ) : (
                  <MessageSquare className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                )}
                <span className="text-sm font-medium truncate">{c.title}</span>
              </div>
              <div className="flex items-center gap-2 mt-1">
                {providerBadge(c.provider)}
                <span className="text-[11px] text-muted-foreground">
                  {t('sa.boss.msgCount', { n: c.msg_count.toLocaleString(locale) })}
                  {c.last_ts &&
                    ` · ${new Date(c.last_ts).toLocaleDateString(locale)}`}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Tin nhắn */}
      <div className="flex-1 overflow-y-auto p-4">
        {selected && <MessageList bossId={bossId} conv={selected} />}
      </div>
    </div>
  );
}
