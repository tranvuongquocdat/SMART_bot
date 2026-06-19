import { useState } from 'react';
import { useSuspenseQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { BarChart } from '@/components/charts';
import { useT } from '@/lib/i18n';
import { errorMessage } from '@/lib/api';
import {
  integrationsQuery,
  integrationUsageQuery,
  setIntegration,
  testIntegration,
} from './api';

const PROVIDER = 'tavily';

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

function IntegrationsContent() {
  const t = useT();
  const qc = useQueryClient();
  const { data: list } = useSuspenseQuery(integrationsQuery());
  const { data: usage } = useSuspenseQuery(integrationUsageQuery(PROVIDER, 30));
  const cfg = list.find((i) => i.provider === PROVIDER) ?? {
    provider: PROVIDER, unit_cost_usd: 0, has_key: false, status: {}, updated_at: null, count: 0, cost: 0,
  };

  const [apiKey, setApiKey] = useState('');
  const [cost, setCost] = useState(String(cfg.unit_cost_usd));

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['superadmin', 'integrations'] });
    qc.invalidateQueries({ queryKey: ['superadmin', 'integration-usage'] });
  };

  const save = useMutation({
    mutationFn: () =>
      setIntegration(PROVIDER, {
        api_key: apiKey.trim() || undefined,
        unit_cost_usd: Number(cost) || 0,
      }),
    onSuccess: () => {
      setApiKey('');
      invalidate();
      toast.success(t('integrations.saved'));
    },
    onError: (e) => toast.error(errorMessage(e, t('integrations.saveFailed'))),
  });

  const test = useMutation({
    mutationFn: () => testIntegration(PROVIDER),
    onSuccess: (r) => {
      invalidate();
      r.ok ? toast.success(t('integrations.keyOk')) : toast.error(r.message || t('integrations.keyBad'));
    },
    onError: (e) => toast.error(errorMessage(e, t('integrations.keyBad'))),
  });

  const st = cfg.status || {};
  const statusBadge =
    st.ok === true ? (
      <Badge variant="default">{t('integrations.status.ok')}</Badge>
    ) : st.ok === false ? (
      <Badge variant="destructive">{t('integrations.status.bad')}</Badge>
    ) : (
      <Badge variant="secondary">{t('integrations.status.unknown')}</Badge>
    );

  return (
    <div className="flex flex-col gap-6">
      {/* Summary */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <SummaryCard label={t('integrations.card.queries')} value={cfg.count.toLocaleString()} />
        <SummaryCard label={t('integrations.card.cost')} value={`$${cfg.cost.toFixed(4)}`} />
        <SummaryCard
          label={t('integrations.card.key')}
          value={cfg.has_key ? (st.ok === false ? t('integrations.status.bad') : t('integrations.status.set')) : t('integrations.status.none')}
          accent={cfg.has_key && st.ok === false}
        />
      </div>

      {/* Config card — Tavily key + unit cost */}
      <div className="rounded-[12px] bg-card-grad surface-section p-5 flex flex-col gap-4 max-w-xl">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">Tavily — {t('integrations.webSearch')}</p>
          {statusBadge}
        </div>
        {st.message && (
          <p className="text-[11px] text-muted-foreground">
            {st.message}{st.checked_at ? ` · ${new Date(st.checked_at).toLocaleString('vi-VN')}` : ''}
          </p>
        )}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="apikey">{t('integrations.apiKey')}</Label>
          <Input
            id="apikey"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={cfg.has_key ? t('integrations.keyPlaceholderSet') : 'tvly-...'}
            autoComplete="off"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cost">{t('integrations.unitCost')}</Label>
          <Input
            id="cost"
            type="number"
            step="0.0001"
            value={cost}
            onChange={(e) => setCost(e.target.value)}
            className="w-40"
          />
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
            {t('integrations.save')}
          </Button>
          <Button size="sm" variant="outline" onClick={() => test.mutate()} disabled={test.isPending || !cfg.has_key}>
            {t('integrations.test')}
          </Button>
        </div>
      </div>

      {/* Cost chart */}
      <div className="rounded-[12px] bg-card-grad surface-section p-4">
        <p className="text-[10px] uppercase tracking-[0.07em] text-[hsl(var(--dim))] font-medium mb-3">
          {t('integrations.chart.dailyCost')}
        </p>
        <BarChart
          data={[...usage.daily].reverse().map((r) => ({
            label: dm(r.date),
            value: r.cost_usd,
            title: `${r.date}: $${r.cost_usd.toFixed(4)} · ${r.count} query`,
          }))}
          emptyText={t('integrations.chart.empty')}
        />
      </div>
    </div>
  );
}

export default function IntegrationsPage() {
  const t = useT();
  return (
    <PageWrap>
      <PageHeader title={t('integrations.title')} subtitle={t('integrations.subtitle')} />
      <PageSection>
        <IntegrationsContent />
      </PageSection>
    </PageWrap>
  );
}
