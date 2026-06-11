import { Check, Minus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { Plan, SubscriptionData } from './api';

type LimitKey =
  | 'max_active_groups'
  | 'max_active_tools'
  | 'max_active_channels'
  | 'mcp_slots'
  | 'cost_cap_usd_daily'
  | 'duration_days';

const ROWS: { key: LimitKey; label: string; fmt: (v: number | null) => string }[] = [
  { key: 'max_active_groups', label: 'Nhóm hoạt động', fmt: (v) => (v === null ? 'Không giới hạn' : `${v} nhóm`) },
  { key: 'max_active_tools', label: 'Tools cho trợ lý', fmt: (v) => (v === null ? 'Không giới hạn' : `${v} tools`) },
  { key: 'max_active_channels', label: 'Kênh kết nối (Zalo…)', fmt: (v) => (v === null ? 'Không giới hạn' : `${v} kênh`) },
  { key: 'mcp_slots', label: 'Integrations ngoài (MCP)', fmt: (v) => (v === null ? 'Không giới hạn' : v === 0 ? '—' : `${v} slot`) },
  { key: 'cost_cap_usd_daily', label: 'Ngân sách AI mỗi ngày', fmt: (v) => (v === null ? 'Không giới hạn' : `$${v}/ngày`) },
  { key: 'duration_days', label: 'Thời hạn gói', fmt: (v) => (v === null ? 'Không giới hạn' : `${v} ngày`) },
];

function CellValue({ value, fmt }: { value: number | null; fmt: (v: number | null) => string }) {
  const text = fmt(value);
  if (text === '—') return <Minus className="h-4 w-4 mx-auto text-muted-foreground/50" />;
  if (text === 'Không giới hạn')
    return (
      <span className="inline-flex items-center gap-1.5">
        <Check className="h-3.5 w-3.5 text-primary" />
        Không giới hạn
      </span>
    );
  return <>{text}</>;
}

export function PlanCards({
  plans,
  current,
  hasPending,
  onSelect,
}: {
  plans: Plan[];
  current: SubscriptionData;
  hasPending: boolean;
  onSelect: (plan: Plan) => void;
}) {
  return (
    <div className="rounded-xl border overflow-x-auto">
      <table className="w-full text-sm border-collapse min-w-[640px]">
        <thead>
          <tr>
            <th className="text-left p-4 w-[220px] align-bottom">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Tính năng
              </span>
            </th>
            {plans.map((plan) => {
              const isCurrent = plan.name === current.plan;
              return (
                <th
                  key={plan.id}
                  className={`p-4 text-center align-bottom ${
                    isCurrent ? 'bg-primary/5 border-x border-t border-primary/30 rounded-t-lg' : ''
                  }`}
                >
                  <div className="space-y-1">
                    <p className="font-semibold text-base">{plan.label}</p>
                    {isCurrent && (
                      <Badge variant="outline" className="text-[10px]">
                        Đang dùng
                      </Badge>
                    )}
                  </div>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row, ri) => (
            <tr key={row.key} className={ri % 2 === 0 ? 'bg-muted/20' : ''}>
              <td className="p-4 text-muted-foreground">{row.label}</td>
              {plans.map((plan) => {
                const isCurrent = plan.name === current.plan;
                return (
                  <td
                    key={plan.id}
                    className={`p-4 text-center tabular-nums ${
                      isCurrent ? 'bg-primary/5 border-x border-primary/30 font-medium' : ''
                    }`}
                  >
                    <CellValue value={plan.limits[row.key] ?? null} fmt={row.fmt} />
                  </td>
                );
              })}
            </tr>
          ))}
          <tr>
            <td className="p-4" />
            {plans.map((plan) => {
              const isCurrent = plan.name === current.plan;
              const disabled = isCurrent || hasPending;
              return (
                <td
                  key={plan.id}
                  className={`p-4 text-center ${
                    isCurrent ? 'bg-primary/5 border-x border-b border-primary/30 rounded-b-lg' : ''
                  }`}
                >
                  <Button
                    size="sm"
                    variant={isCurrent ? 'outline' : 'default'}
                    disabled={disabled}
                    onClick={() => onSelect(plan)}
                    className="w-full max-w-[140px]"
                  >
                    {isCurrent ? 'Đang dùng' : hasPending ? 'Chờ duyệt…' : 'Đăng ký'}
                  </Button>
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
