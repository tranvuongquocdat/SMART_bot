import { useState } from 'react';
import { useSuspenseQuery } from '@tanstack/react-query';
import { BarChart3 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/empty-state';
import { usageQuery } from './api';

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
    <div className="rounded-lg border bg-card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function UsageContent({ range }: { range: RangeValue }) {
  const { data } = useSuspenseQuery(usageQuery(range));

  if (data.totals.messages === 0) {
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
      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <SummaryCard label="Tin nhắn" value={data.totals.messages.toLocaleString('vi-VN')} />
        <SummaryCard label="Tokens" value={data.totals.tokens.toLocaleString('vi-VN')} />
        <SummaryCard label="Chi phí (USD)" value={`$${fmt(data.totals.cost_usd)}`} />
        <SummaryCard
          label="Tokens TB / ngày"
          value={Math.round(data.totals.tokens / data.range_days).toLocaleString('vi-VN')}
        />
      </div>

      {/* Daily breakdown table */}
      <div className="rounded-md border bg-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted-foreground border-b">
              <th className="p-3">Ngày</th>
              <th className="p-3 text-right">Tin nhắn</th>
              <th className="p-3 text-right">Tokens (in)</th>
              <th className="p-3 text-right">Tokens (out)</th>
              <th className="p-3 text-right">Tổng tokens</th>
              <th className="p-3 text-right">Chi phí (USD)</th>
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
  const [range, setRange] = useState<RangeValue>('30d');

  return (
    <div className="flex flex-col gap-6 p-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Sử dụng</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Thống kê tokens và chi phí AI theo ngày.
          </p>
        </div>
        <div className="flex gap-1 rounded-md border p-1 bg-muted/30">
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
      </div>

      <UsageContent range={range} />
    </div>
  );
}
