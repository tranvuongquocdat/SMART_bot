import { useState } from 'react';
import { useSuspenseQuery } from '@tanstack/react-query';
import { BarChart3 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/empty-state';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { BarChart, RankBars } from '@/components/charts';
import { useT } from '@/lib/i18n';
import { platformUsageQuery } from './api';

const RANGES = [
  { value: '7d', days: 7 },
  { value: '30d', days: 30 },
  { value: '90d', days: 90 },
] as const;

type RangeValue = (typeof RANGES)[number]['value'];

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
  const { data } = useSuspenseQuery(platformUsageQuery(range));

  if (data.totals.calls === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title={t('sa.usage.empty')}
        description={t('sa.usage.emptyDesc', { n: data.range_days })}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <SummaryCard label="LLM calls" value={data.totals.calls.toLocaleString('vi-VN')} />
        <SummaryCard label="Tokens" value={data.totals.tokens.toLocaleString('vi-VN')} />
        <SummaryCard label={t('sa.usage.costUsd')} value={`$${fmt(data.totals.cost_usd)}`} />
        <SummaryCard
          label={t('sa.usage.costAvgDay')}
          value={`$${fmt(data.totals.cost_usd / data.range_days)}`}
        />
      </div>

      {/* Daily cost chart — full range, idle days = 0 */}
      {(() => {
        const asc = [...data.daily].reverse();
        const dm = (s: string) => { const [, m, d] = s.split('-'); return `${d}/${m}`; };
        const rangeLabel = asc.length ? `${dm(asc[0].day)} – ${dm(asc[asc.length - 1].day)}` : '';
        return (
          <div className="rounded-[12px] bg-card-grad surface-section p-4">
            <div className="flex items-baseline justify-between mb-3">
              <p className="text-[10px] uppercase tracking-[0.07em] text-[hsl(var(--dim))] font-medium">
                {t('usage.chart.dailyCost')}
              </p>
              <p className="text-[11px] text-muted-foreground tabular-nums">{rangeLabel}</p>
            </div>
            <BarChart
              data={asc.map((r) => ({
                label: dm(r.day),
                value: r.cost_usd,
                title: `${r.day}: $${fmt(r.cost_usd)}`,
              }))}
              emptyText={t('usage.chart.empty')}
            />
          </div>
        );
      })()}

      {/* Cost by model */}
      <div className="rounded-[12px] bg-card-grad surface-section p-4">
        <p className="text-[10px] uppercase tracking-[0.07em] text-[hsl(var(--dim))] font-medium mb-3">
          {t('usage.byModel.title')}
        </p>
        <RankBars
          data={data.by_model.map((m) => ({
            label: m.model,
            value: m.cost_usd,
            sub: `${m.provider} · ${t('usage.byModel.calls', { n: m.calls })}`,
            display: m.cost_usd > 0 ? `$${fmt(m.cost_usd)}` : t('usage.byModel.noCost'),
          }))}
          emptyText={t('usage.chart.empty')}
        />
      </div>

      {/* Per-boss breakdown */}
      <div>
        <h3 className="text-sm font-semibold mb-2">{t('sa.usage.byBoss')}</h3>
        <div className="rounded-[12px] bg-card-grad surface-section overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground border-b">
                <th className="p-3">Boss</th>
                <th className="p-3 text-right">Calls</th>
                <th className="p-3 text-right">Tokens</th>
                <th className="p-3 text-right">{t('sa.usage.costUsd')}</th>
              </tr>
            </thead>
            <tbody>
              {data.by_boss.map(row => (
                <tr key={row.boss_id} className="border-t hover:bg-muted/30 transition-colors">
                  <td className="p-3">
                    <span className="font-medium">{row.name || row.email}</span>
                    {row.name && (
                      <span className="ml-2 text-xs text-muted-foreground">{row.email}</span>
                    )}
                  </td>
                  <td className="p-3 text-right tabular-nums">{row.calls.toLocaleString()}</td>
                  <td className="p-3 text-right tabular-nums">{row.tokens.toLocaleString()}</td>
                  <td className="p-3 text-right tabular-nums font-medium">${fmt(row.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Per-feature breakdown */}
      <div>
        <h3 className="text-sm font-semibold mb-2">{t('sa.usage.byFeature')}</h3>
        <div className="rounded-[12px] bg-card-grad surface-section overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground border-b">
                <th className="p-3">{t('sa.usage.colFeature')}</th>
                <th className="p-3 text-right">Calls</th>
                <th className="p-3 text-right">Tokens</th>
                <th className="p-3 text-right">{t('sa.usage.costUsd')}</th>
              </tr>
            </thead>
            <tbody>
              {data.by_feature.map(row => (
                <tr key={row.feature} className="border-t hover:bg-muted/30 transition-colors">
                  <td className="p-3 font-mono text-xs">{row.feature}</td>
                  <td className="p-3 text-right tabular-nums">{row.calls.toLocaleString()}</td>
                  <td className="p-3 text-right tabular-nums">{row.tokens.toLocaleString()}</td>
                  <td className="p-3 text-right tabular-nums font-medium">${fmt(row.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Daily breakdown */}
      <div>
        <h3 className="text-sm font-semibold mb-2">{t('sa.usage.byDay')}</h3>
        <div className="rounded-[12px] bg-card-grad surface-section overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground border-b">
                <th className="p-3">{t('sa.usage.colDate')}</th>
                <th className="p-3 text-right">Calls</th>
                <th className="p-3 text-right">Tokens</th>
                <th className="p-3 text-right">{t('sa.usage.costUsd')}</th>
              </tr>
            </thead>
            <tbody>
              {data.daily.map(row => (
                <tr key={row.day} className="border-t hover:bg-muted/30 transition-colors">
                  <td className="p-3 font-mono text-xs">{row.day}</td>
                  <td className="p-3 text-right tabular-nums">{row.calls.toLocaleString()}</td>
                  <td className="p-3 text-right tabular-nums">{row.tokens.toLocaleString()}</td>
                  <td className="p-3 text-right tabular-nums font-medium">${fmt(row.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function PlatformUsagePage() {
  const t = useT();
  const [range, setRange] = useState<RangeValue>('30d');

  return (
    <PageWrap>
      <PageHeader
        title={t('nav.sa.usage')}
        subtitle={t('sa.usage.subtitle')}
        actions={
          <div className="flex gap-1 rounded-md border border-border p-1 bg-[hsl(var(--muted))]">
            {RANGES.map(r => (
              <Button
                key={r.value}
                variant={range === r.value ? 'default' : 'ghost'}
                size="sm"
                className="h-7 text-xs px-3"
                onClick={() => setRange(r.value)}
              >
                {t('sa.acct.days', { n: r.days })}
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
