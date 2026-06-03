import { relativeTime } from '@/lib/format';
import type { Summary } from './api';

export function SummaryCard({ summary }: { summary: Summary }) {
  return (
    <div className="rounded-xl bg-card p-5 mb-5 relative overflow-hidden shadow-[0_0_0_1px_hsl(var(--border-strong)),0_1px_2px_rgba(0,0,0,.04)]">
      <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-gradient-to-b from-primary to-transparent opacity-50" />
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] uppercase tracking-wider text-primary font-medium inline-flex items-center gap-1.5 before:content-[''] before:h-1 before:w-1 before:rounded-full before:bg-primary">
          Tóm tắt hôm nay
        </span>
        <span className="text-xs text-[hsl(var(--dim))]">
          {summary.updated_at ? `Cập nhật ${relativeTime(summary.updated_at)}` : 'Chưa có'}
        </span>
      </div>
      {summary.body ? (
        <div className="text-sm leading-[1.7] whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: summary.body }} />
      ) : (
        <p className="text-sm text-muted-foreground">Chưa có tóm tắt cho hôm nay.</p>
      )}
    </div>
  );
}
