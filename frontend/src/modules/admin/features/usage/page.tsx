import { useState } from 'react';
import { useSuspenseQuery } from '@tanstack/react-query';
import { BarChart3 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/empty-state';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { useT } from '@/lib/i18n';
import { usageQuery } from './api';

const RANGE_VALUES = ['7d', '30d', '90d'] as const;
type RangeValue = (typeof RANGE_VALUES)[number];

function fmt(n: number, decimals = 4) {
  return n.toLocaleString('vi-VN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[12px] bg-card-grad surface-section p-4">
      <p className="text-[10px] uppercase tracking-[0.07em] text-[hsl(var(--dim))] font-medium">{label}</p>
      <p className="mt-1 text-[22px] font-semibold tracking-[-0.02em] tabular-nums">{value}</p>
    </div>
  );
}

function UsageContent({ range }: { range: RangeValue }) {
  const t = useT();
  const { data } = useSuspenseQuery(usageQuery(range));

  if (data.totals.messages === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title={t('usage.empty.title')}
        description={t('usage.empty.desc', { n: data.range_days })}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <SummaryCard label={t('usage.card.messages')} value={data.totals.messages.toLocaleString()} />
        <SummaryCard label={t('usage.card.tokens')} value={data.totals.tokens.toLocaleString()} />
        <SummaryCard label={t('usage.card.cost')} value={`$${fmt(data.totals.cost_usd)}`} />
        <SummaryCard
          label={t('usage.card.avgTokens')}
          value={Math.round(data.totals.tokens / data.range_days).toLocaleString()}
        />
      </div>

      {/* Daily breakdown table */}
      <div className="rounded-[12px] bg-card-grad surface-section overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted-foreground border-b">
              <th className="p-3">{t('usage.col.date')}</th>
              <th className="p-3 text-right">{t('usage.col.messages')}</th>
              <th className="p-3 text-right">{t('usage.col.tokensIn')}</th>
              <th className="p-3 text-right">{t('usage.col.tokensOut')}</th>
              <th className="p-3 text-right">{t('usage.col.tokensTotal')}</th>
              <th className="p-3 text-right">{t('usage.col.cost')}</th>
            </tr>
          </thead>
          <tbody>
            {data.daily.map(row => (
              <tr key={row.date} className="border-t hover:bg-muted/30 transition-colors">
                <td className="p-3 font-mono text-xs">{row.date}</td>
                <td className="p-3 text-right tabular-nums">{row.messages}</td>
                <td className="p-3 text-right tabular-nums text-muted-foreground">
                  {row.tokens_in.toLocaleString()}
                </td>
                <td className="p-3 text-right tabular-nums text-muted-foreground">
                  {row.tokens_out.toLocaleString()}
                </td>
                <td className="p-3 text-right tabular-nums">{row.tokens.toLocaleString()}</td>
                <td className="p-3 text-right tabular-nums font-medium">
                  ${fmt(row.cost_usd)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function UsagePage() {
  const t = useT();
  const [range, setRange] = useState<RangeValue>('30d');

  return (
    <PageWrap>
      <PageHeader
        title={t('usage.title')}
        subtitle={t('usage.subtitle')}
        actions={
          <div className="flex gap-1 rounded-md border border-border p-1 bg-[hsl(var(--muted))]">
            {RANGE_VALUES.map(rv => (
              <Button
                key={rv}
                variant={range === rv ? 'default' : 'ghost'}
                size="sm"
                className="h-7 text-xs px-3"
                onClick={() => setRange(rv)}
              >
                {t(`usage.range.${rv}`)}
              </Button>
            ))}
          </div>
        }
      />

      <PageSection>
        <UsageContent range={range} />
      </PageSection>
    </PageWrap>
  );
}
