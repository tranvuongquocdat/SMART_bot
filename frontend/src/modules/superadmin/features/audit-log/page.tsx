import { useState, useCallback, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FileText, Search } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/empty-state';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { useT } from '@/lib/i18n';
import { fetchAuditLog } from './api';
import type { AuditLogItem } from './api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function actionColor(action: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (action.startsWith('delete') || action.startsWith('remove')) return 'destructive';
  if (action.startsWith('create') || action.startsWith('add')) return 'default';
  if (action.startsWith('update') || action.startsWith('patch')) return 'secondary';
  return 'outline';
}

// ---------------------------------------------------------------------------
// Row
// ---------------------------------------------------------------------------

function AuditRow({ item }: { item: AuditLogItem }) {
  const actor = item.actor_email ?? `uid:${item.actor_user_id}`;
  const target = [item.target_kind, item.target_id].filter(Boolean).join('/') || '—';

  return (
    <tr className="border-row hover:bg-[hsl(var(--hover))] transition-colors">
      <td className="px-4 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
        <span title={new Date(item.created_at).toLocaleString('vi-VN')}>
          {relativeTime(item.created_at)}
        </span>
      </td>
      <td className="px-4 py-2.5">
        <span className="font-mono text-xs">{actor}</span>
        {item.actor_name && (
          <div className="text-xs text-muted-foreground mt-0.5">{item.actor_name}</div>
        )}
      </td>
      <td className="px-4 py-2.5">
        <Badge variant={actionColor(item.action)} className="font-mono text-xs">
          {item.action}
        </Badge>
      </td>
      <td className="px-4 py-2.5 text-xs text-muted-foreground font-mono">{target}</td>
      <td className="px-4 py-2.5 text-xs font-mono text-muted-foreground max-w-[220px] truncate">
        {item.payload_json ? JSON.stringify(item.payload_json) : ''}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AuditLogPage() {
  const t = useT();
  const [actorFilter, setActorFilter] = useState('');
  const [actionFilter, setActionFilter] = useState('');
  const [appliedActor, setAppliedActor] = useState('');
  const [appliedAction, setAppliedAction] = useState('');
  const [allItems, setAllItems] = useState<AuditLogItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const queryKey = ['superadmin', 'audit-log', appliedActor, appliedAction] as const;

  const result = useQuery({
    queryKey,
    queryFn: () => fetchAuditLog({ actor: appliedActor || undefined, action: appliedAction || undefined }),
  });

  // Sync first-page results into local state
  useEffect(() => {
    if (result.data) {
      setAllItems(result.data.items);
      setNextCursor(result.data.next_cursor);
    }
  }, [result.data]);

  const applyFilters = useCallback(() => {
    setAllItems([]);
    setNextCursor(null);
    setAppliedActor(actorFilter);
    setAppliedAction(actionFilter);
  }, [actorFilter, actionFilter]);

  const loadMore = useCallback(async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await fetchAuditLog({
        cursor: nextCursor,
        actor: appliedActor || undefined,
        action: appliedAction || undefined,
      });
      setAllItems(prev => [...prev, ...page.items]);
      setNextCursor(page.next_cursor);
    } finally {
      setLoadingMore(false);
    }
  }, [nextCursor, loadingMore, appliedActor, appliedAction]);

  return (
    <PageWrap>
      <PageHeader
        title={t('nav.sa.audit')}
        subtitle={t('sa.audit.subtitle')}
      />

      <PageSection>
        <div className="flex gap-2 flex-wrap">
          <Input
            placeholder={t('sa.audit.actorPlaceholder')}
            value={actorFilter}
            onChange={e => setActorFilter(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && applyFilters()}
            className="w-52"
          />
          <Input
            placeholder={t('sa.audit.actionPlaceholder')}
            value={actionFilter}
            onChange={e => setActionFilter(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && applyFilters()}
            className="w-52"
          />
          <Button variant="secondary" size="default" onClick={applyFilters}>
            <Search className="h-3.5 w-3.5 mr-1" />
            {t('sa.audit.filter')}
          </Button>
        </div>
      </PageSection>

      <PageSection>
        {result.isLoading ? (
          <Skeleton className="h-[320px] rounded-[12px]" />
        ) : result.isError ? (
          <p className="text-destructive text-sm py-4">{t('sa.audit.loadError')}</p>
        ) : allItems.length === 0 ? (
          <EmptyState icon={FileText} title={t('sa.audit.empty')} />
        ) : (
          <div className="rounded-[12px] bg-card-grad surface-section overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-[hsl(var(--muted))]">
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">{t('sa.audit.colTime')}</th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Actor</th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Action</th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Target</th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Payload</th>
                </tr>
              </thead>
              <tbody>
                {allItems.map(item => (
                  <AuditRow key={item.id} item={item} />
                ))}
              </tbody>
            </table>

            {nextCursor && (
              <div className="flex justify-center py-3 border-t border-border">
                <Button variant="outline" size="sm" onClick={loadMore} disabled={loadingMore}>
                  {loadingMore ? t('sa.common.loading') : t('sa.audit.loadMore')}
                </Button>
              </div>
            )}
          </div>
        )}
      </PageSection>
    </PageWrap>
  );
}
