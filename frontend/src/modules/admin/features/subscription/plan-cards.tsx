import { Check, Minus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useT } from '@/lib/i18n';
import type { BillingPeriod, Plan, SubscriptionData } from './api';

const fmtVnd = (v: number) => new Intl.NumberFormat('vi-VN').format(v) + 'đ';

type LimitKey =
  | 'max_active_groups'
  | 'max_active_tools'
  | 'max_active_channels'
  | 'mcp_slots'
  | 'cost_cap_usd_daily'
  | 'duration_days';

type T = (key: string, vars?: Record<string, string | number>) => string;

const ROWS: { key: LimitKey; labelKey: string; valKey: string }[] = [
  { key: 'max_active_groups', labelKey: 'sub.row.groups', valKey: 'sub.val.groups' },
  { key: 'max_active_tools', labelKey: 'sub.row.tools', valKey: 'sub.val.tools' },
  { key: 'max_active_channels', labelKey: 'sub.row.channels', valKey: 'sub.val.channels' },
  { key: 'mcp_slots', labelKey: 'sub.row.mcp', valKey: 'sub.val.mcp' },
  { key: 'cost_cap_usd_daily', labelKey: 'sub.row.cost', valKey: 'sub.val.cost' },
  { key: 'duration_days', labelKey: 'sub.row.duration', valKey: 'sub.val.duration' },
];

function CellValue({
  value,
  valKey,
  t,
}: {
  value: number | null;
  valKey: string;
  t: T;
}) {
  if (value === null)
    return (
      <span className="inline-flex items-center gap-1.5">
        <Check className="h-3.5 w-3.5 text-primary" />
        {t('sub.unlimited')}
      </span>
    );
  if (valKey === 'sub.val.mcp' && value === 0)
    return <Minus className="h-4 w-4 mx-auto text-muted-foreground/50" />;
  return <>{t(valKey, { n: value })}</>;
}

export function PlanCards({
  plans,
  current,
  hasPending,
  period,
  onSelect,
}: {
  plans: Plan[];
  current: SubscriptionData;
  hasPending: boolean;
  period: BillingPeriod;
  onSelect: (plan: Plan) => void;
}) {
  const t = useT();
  return (
    <div className="rounded-xl border overflow-x-auto">
      <table className="w-full text-sm border-collapse min-w-[640px]">
        <thead>
          <tr>
            <th className="text-left p-4 w-[220px] align-bottom">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                {t('sub.feature')}
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
                    <p className="text-sm font-normal text-muted-foreground tabular-nums">
                      {plan.prices?.[period] != null ? (
                        <>
                          <span className="font-semibold text-foreground">
                            {fmtVnd(plan.prices[period]!)}
                          </span>
                          {t('sub.perMonths', { n: period })}
                        </>
                      ) : plan.name === 'trial' ? (
                        t('sub.free')
                      ) : (
                        t('sub.contact')
                      )}
                    </p>
                    {isCurrent && (
                      <Badge variant="outline" className="text-[10px]">
                        {t('sub.current')}
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
              <td className="p-4 text-muted-foreground">{t(row.labelKey)}</td>
              {plans.map((plan) => {
                const isCurrent = plan.name === current.plan;
                return (
                  <td
                    key={plan.id}
                    className={`p-4 text-center tabular-nums ${
                      isCurrent ? 'bg-primary/5 border-x border-primary/30 font-medium' : ''
                    }`}
                  >
                    {row.key === 'duration_days' &&
                    plan.prices &&
                    Object.keys(plan.prices).length > 0 ? (
                      <>{t('sub.byCycle')}</>
                    ) : (
                      <CellValue value={plan.limits[row.key] ?? null} valKey={row.valKey} t={t} />
                    )}
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
                    {isCurrent ? t('sub.current') : hasPending ? t('sub.waiting') : t('sub.subscribe')}
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
