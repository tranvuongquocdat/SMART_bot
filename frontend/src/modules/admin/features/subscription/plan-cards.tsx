import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { Plan, SubscriptionData } from './api';

function fmt(v: number | null) {
  return v === null ? '∞' : String(v);
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
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {plans.map((plan) => {
        const isCurrent = plan.name === current.plan;
        const disabled = isCurrent || hasPending;
        return (
          <div
            key={plan.id}
            className={`rounded-xl border p-4 flex flex-col gap-3 transition-colors ${
              isCurrent
                ? 'border-primary bg-primary/5'
                : 'border-border bg-card hover:bg-muted/40'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-semibold text-sm">{plan.label}</span>
              {isCurrent && (
                <Badge variant="outline" className="text-xs">
                  Đang dùng
                </Badge>
              )}
            </div>
            <ul className="text-xs text-muted-foreground space-y-0.5 flex-1">
              <li>{fmt(plan.limits.max_active_groups)} nhóm</li>
              <li>{fmt(plan.limits.max_active_tools)} tools</li>
              <li>{fmt(plan.limits.max_active_channels)} kênh</li>
              {plan.limits.mcp_slots !== null && (
                <li>{fmt(plan.limits.mcp_slots)} integrations</li>
              )}
              {plan.limits.duration_days && (
                <li>{plan.limits.duration_days} ngày</li>
              )}
            </ul>
            <Button
              size="sm"
              variant={isCurrent ? 'outline' : 'default'}
              disabled={disabled}
              onClick={() => onSelect(plan)}
              className="mt-auto w-full"
            >
              {isCurrent
                ? 'Đang dùng'
                : hasPending
                  ? 'Đang chờ duyệt...'
                  : 'Đăng ký'}
            </Button>
          </div>
        );
      })}
    </div>
  );
}
