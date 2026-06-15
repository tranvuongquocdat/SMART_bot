/**
 * Lightweight dependency-free charts (div/flex based) khớp design-system.
 * - BarChart: cột dọc theo thời gian (xu hướng).
 * - RankBars: thanh ngang xếp hạng (vd chi phí theo model).
 */
import { cn } from '@/lib/utils';

type BarDatum = { label: string; value: number; title?: string };

export function BarChart({
  data,
  height = 120,
  className,
  emptyText,
}: {
  data: BarDatum[];
  height?: number;
  className?: string;
  emptyText?: string;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  if (data.length === 0) {
    return (
      <div className="text-xs text-muted-foreground py-8 text-center">{emptyText ?? '—'}</div>
    );
  }
  // Nhãn thưa: chỉ hiện ~6 mốc để không chật.
  const step = Math.max(1, Math.ceil(data.length / 6));
  return (
    <div className={cn('w-full', className)}>
      <div className="flex items-end gap-[3px]" style={{ height }}>
        {data.map((d, i) => (
          <div
            key={i}
            className="flex-1 min-w-0 rounded-t-sm bg-primary/70 hover:bg-primary transition-colors"
            style={{ height: `${Math.max(2, (d.value / max) * 100)}%` }}
            title={d.title ?? `${d.label}: ${d.value}`}
          />
        ))}
      </div>
      <div className="flex gap-[3px] mt-1">
        {data.map((d, i) => (
          <div key={i} className="flex-1 min-w-0 text-center text-[9px] text-[hsl(var(--dim))] tabular-nums">
            {i % step === 0 ? d.label : ''}
          </div>
        ))}
      </div>
    </div>
  );
}

type RankDatum = { label: string; value: number; sub?: string; display: string };

export function RankBars({
  data,
  className,
  emptyText,
}: {
  data: RankDatum[];
  className?: string;
  emptyText?: string;
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  if (data.length === 0) {
    return (
      <div className="text-xs text-muted-foreground py-6 text-center">{emptyText ?? '—'}</div>
    );
  }
  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {data.map((d, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="w-40 shrink-0 min-w-0">
            <p className="text-[13px] font-medium truncate">{d.label}</p>
            {d.sub && <p className="text-[11px] text-[hsl(var(--dim))] truncate">{d.sub}</p>}
          </div>
          <div className="flex-1 h-2.5 rounded-full bg-muted/50 overflow-hidden">
            <div
              className="h-full rounded-full bg-primary/70"
              style={{ width: `${Math.max(2, (d.value / max) * 100)}%` }}
            />
          </div>
          <div className="w-24 shrink-0 text-right text-[13px] font-medium tabular-nums">
            {d.display}
          </div>
        </div>
      ))}
    </div>
  );
}
