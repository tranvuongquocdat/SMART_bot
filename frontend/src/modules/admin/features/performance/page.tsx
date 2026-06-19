import { Suspense, useState } from 'react';
import { useSuspenseQuery } from '@tanstack/react-query';
import { BarChart3, Loader2 } from 'lucide-react';
import { EmptyState } from '@/components/empty-state';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { RankBars } from '@/components/charts';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { groupsListQuery } from '@/modules/admin/features/groups/api';
import { useT } from '@/lib/i18n';
import { workloadQuery } from './api';

const ALL_GROUPS = '__all__';

// "2026-06-10" → "10/6"
function dm(s: string) {
  const [, m, d] = s.split('-');
  return `${parseInt(d, 10)}/${parseInt(m, 10)}`;
}

function SummaryCard({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-[12px] bg-card-grad surface-section p-4">
      <p className="text-[10px] uppercase tracking-[0.07em] text-[hsl(var(--dim))] font-medium">{label}</p>
      <p
        className={
          'mt-1 text-[22px] font-semibold tracking-[-0.02em] tabular-nums' +
          (accent ? ' text-[hsl(var(--destructive))]' : '')
        }
      >
        {value}
      </p>
    </div>
  );
}

function PerfContent({ groupId }: { groupId: string | null }) {
  const t = useT();
  const { data } = useSuspenseQuery(workloadQuery(groupId));

  if (data.totals.open + data.totals.done === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title={t('perf.empty.title')}
        description={t('perf.empty.desc')}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <SummaryCard label={t('perf.card.people')} value={data.totals.assignees.toLocaleString()} />
        <SummaryCard label={t('perf.card.open')} value={data.totals.open.toLocaleString()} />
        <SummaryCard
          label={t('perf.card.overdue')}
          value={data.totals.overdue.toLocaleString()}
          accent={data.totals.overdue > 0}
        />
        <SummaryCard label={t('perf.card.done')} value={data.totals.done.toLocaleString()} />
      </div>

      {/* Workload by person — bar = số việc đang mở; xếp người tải nặng / quá hạn lên trước */}
      <div className="rounded-[12px] bg-card-grad surface-section p-4">
        <p className="text-[10px] uppercase tracking-[0.07em] text-[hsl(var(--dim))] font-medium mb-3">
          {t('perf.byPerson.title')}
        </p>
        <RankBars
          data={data.by_assignee.map((a) => ({
            label: a.assignee,
            value: a.open,
            sub: [
              a.overdue > 0 ? `${a.overdue} ${t('perf.overdue')}` : null,
              `${a.done} ${t('perf.done')}`,
              a.completion_rate != null ? `${Math.round(a.completion_rate * 100)}% ${t('perf.rate')}` : null,
            ]
              .filter(Boolean)
              .join(' · '),
            display: t('perf.openCount', { n: a.open }),
          }))}
          emptyText={t('perf.empty.desc')}
        />
      </div>

      {/* Overdue items — nêu rõ việc nào, ai, hạn */}
      {data.overdue_items.length > 0 && (
        <div className="rounded-[12px] bg-card-grad surface-section overflow-x-auto">
          <p className="text-[10px] uppercase tracking-[0.07em] text-[hsl(var(--dim))] font-medium p-4 pb-2">
            {t('perf.overdueList.title')}
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground border-b">
                <th className="p-3">{t('perf.col.what')}</th>
                <th className="p-3">{t('perf.col.assignee')}</th>
                <th className="p-3 text-right">{t('perf.col.due')}</th>
              </tr>
            </thead>
            <tbody>
              {data.overdue_items.map((it, i) => (
                <tr key={i} className="border-t hover:bg-muted/30 transition-colors">
                  <td className="p-3">{it.what}</td>
                  <td className="p-3">{it.assignee}</td>
                  <td className="p-3 text-right tabular-nums text-[hsl(var(--destructive))]">{dm(it.due)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function GroupFilter({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (v: string | null) => void;
}) {
  const t = useT();
  const { data: groups } = useSuspenseQuery(groupsListQuery());
  return (
    <Select
      value={value ?? ALL_GROUPS}
      onValueChange={(v) => onChange(v === ALL_GROUPS ? null : v)}
    >
      <SelectTrigger className="h-8 w-[200px] text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL_GROUPS}>{t('perf.filter.allGroups')}</SelectItem>
        {groups.map((g) => (
          <SelectItem key={g.chat_id} value={g.chat_id}>
            {g.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export default function PerformancePage() {
  const t = useT();
  const [groupId, setGroupId] = useState<string | null>(null);
  return (
    <PageWrap>
      <PageHeader
        title={t('perf.title')}
        subtitle={t('perf.subtitle')}
        actions={<GroupFilter value={groupId} onChange={setGroupId} />}
      />
      <PageSection>
        <Suspense
          fallback={
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          }
        >
          <PerfContent groupId={groupId} />
        </Suspense>
      </PageSection>
    </PageWrap>
  );
}
