import { useState } from 'react';
import { useSuspenseQuery } from '@tanstack/react-query';
import { BarChart3 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/empty-state';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { platformUsageQuery } from './api';

const RANGES = [
  { value: '7d', label: '7 ngày' },
  { value: '30d', label: '30 ngày' },
  { value: '90d', label: '90 ngày' },
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
  const { data } = useSuspenseQuery(platformUsageQuery(range));

  if (data.totals.calls === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title="Chưa có dữ liệu sử dụng"
        description={`Không có hoạt động nào trong ${data.range_days} ngày qua.`}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <SummaryCard label="LLM calls" value={data.totals.calls.toLocaleString('vi-VN')} />
        <SummaryCard label="Tokens" value={data.totals.tokens.toLocaleString('vi-VN')} />
        <SummaryCard label="Chi phí (USD)" value={`$${fmt(data.totals.cost_usd)}`} />
        <SummaryCard
          label="Chi phí TB / ngày"
          value={`$${fmt(data.totals.cost_usd / data.range_days)}`}
        />
      </div>

      {/* Per-boss breakdown */}
      <div>
        <h3 className="text-sm font-semibold mb-2">Theo boss</h3>
        <div className="rounded-[12px] bg-card-grad surface-section overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground border-b">
                <th className="p-3">Boss</th>
                <th className="p-3 text-right">Calls</th>
                <th className="p-3 text-right">Tokens</th>
                <th className="p-3 text-right">Chi phí (USD)</th>
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
        <h3 className="text-sm font-semibold mb-2">Theo tính năng</h3>
        <div className="rounded-[12px] bg-card-grad surface-section overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground border-b">
                <th className="p-3">Tính năng</th>
                <th className="p-3 text-right">Calls</th>
                <th className="p-3 text-right">Tokens</th>
                <th className="p-3 text-right">Chi phí (USD)</th>
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
        <h3 className="text-sm font-semibold mb-2">Theo ngày</h3>
        <div className="rounded-[12px] bg-card-grad surface-section overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground border-b">
                <th className="p-3">Ngày</th>
                <th className="p-3 text-right">Calls</th>
                <th className="p-3 text-right">Tokens</th>
                <th className="p-3 text-right">Chi phí (USD)</th>
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
  const [range, setRange] = useState<RangeValue>('30d');

  return (
    <PageWrap>
      <PageHeader
        title="Sử dụng"
        subtitle="Thống kê tokens và chi phí AI toàn nền tảng — theo boss, tính năng, ngày."
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
                {r.label}
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
