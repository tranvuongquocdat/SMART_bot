import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Maximize2, Minimize2, X } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { drawerBackdrop, drawerPanel, tabFade } from '@/lib/motion';
import { errorMessage } from '@/lib/api';
import { useT, useI18n } from '@/lib/i18n';
import { plansAdminQuery } from '../plans/api';
import { proxiesQuery, setBossProxy } from '../proxies/api';
import {
  bossOverviewQuery,
  patchBossSubscription,
  type Boss,
  type BossOverview,
  type UsageGauge,
} from './api';
import { BossAiTab } from './drawer-ai-tab';
import { BossChatTab } from './drawer-chat-tab';

const MIN_W = 520;
const DEFAULT_W = 720;

const TABS = [
  { key: 'overview', labelKey: 'sa.boss.tabOverview' },
  { key: 'subscription', labelKey: 'sa.boss.tabSub' },
  { key: 'ai', labelKey: 'sa.boss.tabAi' },
  { key: 'chat', labelKey: 'sa.boss.tabChat' },
] as const;
type TabKey = (typeof TABS)[number]['key'];

const fmtUsd = (v: number) => `$${v.toFixed(2)}`;

// ------------------------------------------------------------- Tổng quan

function Gauge({ label, gauge }: { label: string; gauge: UsageGauge }) {
  const over = gauge.limit != null && gauge.used > gauge.limit;
  return (
    <div className="rounded-lg border bg-card px-3 py-2.5">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={`text-lg font-semibold tabular-nums ${over ? 'text-destructive' : ''}`}>
        {gauge.used}
        <span className="text-sm font-normal text-muted-foreground">
          {' '}/ {gauge.limit ?? '∞'}
        </span>
      </p>
    </div>
  );
}

function ProxySection({ bossId, data }: { bossId: number; data: BossOverview }) {
  const t = useT();
  const qc = useQueryClient();
  const proxies = useQuery(proxiesQuery);
  const current = data.proxy;

  const mut = useMutation({
    mutationFn: (proxyId: number | null) => setBossProxy(bossId, proxyId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'boss', bossId] });
      qc.invalidateQueries({ queryKey: ['superadmin', 'proxies'] });
      toast.success(t('sa.boss.proxyUpdated'));
    },
    onError: (e) => toast.error(errorMessage(e, t('sa.boss.proxyUpdateError'))),
  });

  return (
    <div className="rounded-lg border bg-card px-3 py-2.5 space-y-2">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{t('sa.boss.proxyTitle')}</p>
      <div className="flex items-center gap-2">
        <Select
          value={current ? String(current.id) : 'none'}
          onValueChange={(v) => mut.mutate(v === 'none' ? null : Number(v))}
          disabled={mut.isPending}
        >
          <SelectTrigger className="h-8 text-sm flex-1">
            <SelectValue placeholder={t('sa.boss.unassigned')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">{t('sa.boss.noProxy')}</SelectItem>
            {(proxies.data ?? [])
              .filter((p) => p.status === 'active')
              .map((p) => (
                <SelectItem
                  key={p.id}
                  value={String(p.id)}
                  disabled={p.assigned_count >= p.max_bosses && current?.id !== p.id}
                >
                  {p.label}
                  {p.region ? ` · ${p.region}` : ''} ({p.assigned_count}/{p.max_bosses})
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
      </div>
      <p className="text-[11px] text-muted-foreground">
        {t('sa.boss.proxyNote')}
      </p>
    </div>
  );
}

function OverviewTab({ bossId, data }: { bossId: number; data: BossOverview }) {
  const t = useT();
  const { lang } = useI18n();
  const locale = lang === 'en' ? 'en-US' : 'vi-VN';
  const u = data.usage;
  return (
    <div className="space-y-5">
      <ProxySection bossId={bossId} data={data} />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Gauge label={t('sa.boss.gaugeGroups')} gauge={u.groups} />
        <Gauge label="Tools" gauge={u.tools} />
        <Gauge label={t('sa.boss.gaugeChannels')} gauge={u.channels} />
        <Gauge label="MCP" gauge={u.mcp} />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="rounded-lg border bg-card px-3 py-2.5">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {t('sa.boss.costToday')}
          </p>
          <p className="text-lg font-semibold tabular-nums">
            {fmtUsd(u.cost_today_usd)}
            <span className="text-sm font-normal text-muted-foreground">
              {' '}/ {u.cost_cap_usd_daily != null ? fmtUsd(u.cost_cap_usd_daily) : '∞'}
            </span>
          </p>
        </div>
        <div className="rounded-lg border bg-card px-3 py-2.5">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {t('sa.boss.cost30d')}
          </p>
          <p className="text-lg font-semibold tabular-nums">{fmtUsd(u.cost_30d_usd)}</p>
          <p className="text-xs text-muted-foreground tabular-nums">
            {t('sa.boss.tokensSuffix', { n: u.tokens_30d.toLocaleString(locale) })}
          </p>
        </div>
        <div className="rounded-lg border bg-card px-3 py-2.5">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {t('sa.boss.msgs30d')}
          </p>
          <p className="text-lg font-semibold tabular-nums">
            {u.msgs_in_30d.toLocaleString(locale)}
            <span className="text-sm font-normal text-muted-foreground"> {t('sa.boss.received')}</span>
          </p>
          <p className="text-xs text-muted-foreground tabular-nums">
            {t('sa.boss.botReplied', { n: u.msgs_out_30d.toLocaleString(locale) })}
          </p>
        </div>
      </div>

      <div className="text-sm space-y-1.5">
        <p>
          <span className="text-muted-foreground">{t('sa.boss.plan')}</span>{' '}
          <span className="font-medium">{data.subscription.plan_label ?? '—'}</span>
          {data.subscription.status && (
            <Badge variant="secondary" className="ml-2 text-[10px] capitalize">
              {data.subscription.status}
            </Badge>
          )}
        </p>
        <p>
          <span className="text-muted-foreground">{t('sa.boss.expiry')}</span>{' '}
          {data.subscription.expiry
            ? new Date(data.subscription.expiry).toLocaleDateString(locale)
            : t('sa.boss.unlimited')}
        </p>
        <p>
          <span className="text-muted-foreground">{t('sa.boss.channels')}</span>{' '}
          {u.channel_list.length > 0
            ? u.channel_list
                .map((c) => `${c.provider}${c.display_name ? ` (${c.display_name})` : ''}`)
                .join(', ')
            : t('sa.boss.notConnected')}
        </p>
        <p>
          <span className="text-muted-foreground">{t('sa.boss.lastActive')}</span>{' '}
          {u.last_message_at
            ? new Date(u.last_message_at).toLocaleString(locale)
            : t('sa.boss.noMessages')}
        </p>
        {Object.keys(data.subscription.overrides).length > 0 && (
          <p>
            <span className="text-muted-foreground">{t('sa.boss.override')}</span>{' '}
            {Object.entries(data.subscription.overrides)
              .map(([k, v]) => `${k}=${v}`)
              .join(', ')}
          </p>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------- Gói & giới hạn

const OVERRIDE_FIELDS: { key: string; labelKey: string }[] = [
  { key: 'max_active_groups', labelKey: 'sa.boss.ovMaxGroups' },
  { key: 'max_active_tools', labelKey: 'sa.boss.ovMaxTools' },
  { key: 'max_active_channels', labelKey: 'sa.boss.ovMaxChannels' },
  { key: 'mcp_slots', labelKey: 'MCP slots' },
  { key: 'cost_cap_usd_daily', labelKey: 'sa.boss.ovUsdDay' },
];

const STATUS_OPTIONS = ['trial', 'active', 'expired_grace', 'expired', 'canceled'];

function SubscriptionTab({ bossId, data }: { bossId: number; data: BossOverview }) {
  const t = useT();
  const qc = useQueryClient();
  const plans = useQuery(plansAdminQuery());

  const [planId, setPlanId] = useState<string>(String(data.subscription.plan_id ?? ''));
  const [status, setStatus] = useState<string>(data.subscription.status ?? 'trial');
  const [expiry, setExpiry] = useState<string>(
    data.subscription.expiry ? data.subscription.expiry.slice(0, 10) : ''
  );
  const [overrides, setOverrides] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      OVERRIDE_FIELDS.map((f) => [
        f.key,
        data.subscription.overrides[f.key] != null
          ? String(data.subscription.overrides[f.key])
          : '',
      ])
    )
  );

  const mut = useMutation({
    mutationFn: () => {
      const body: Parameters<typeof patchBossSubscription>[1] = {
        subscription_status: status,
        overrides: Object.fromEntries(
          OVERRIDE_FIELDS.map((f) => [
            f.key,
            overrides[f.key] === '' ? null : Number(overrides[f.key]),
          ])
        ),
      };
      if (planId) body.plan_id = Number(planId);
      if (expiry) body.subscription_expiry = `${expiry}T23:59:59+07:00`;
      else body.clear_expiry = true;
      return patchBossSubscription(bossId, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'boss', bossId] });
      qc.invalidateQueries({ queryKey: ['superadmin', 'bosses'] });
      toast.success(t('sa.boss.subSaved'));
    },
    onError: (e) => toast.error(errorMessage(e, t('sa.boss.subSaveError'))),
  });

  return (
    <div className="space-y-5 max-w-md">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">{t('sa.boss.planLabel')}</Label>
          <Select value={planId || undefined} onValueChange={setPlanId}>
            <SelectTrigger className="h-8 text-sm">
              <SelectValue placeholder={t('sa.boss.planPlaceholder')} />
            </SelectTrigger>
            <SelectContent>
              {(plans.data ?? []).map((p) => (
                <SelectItem key={p.id} value={String(p.id)}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{t('sa.boss.statusLabel')}</Label>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="h-8 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">{t('sa.boss.expiryDateLabel')}</Label>
        <Input
          type="date"
          className="h-8 text-sm w-44"
          value={expiry}
          onChange={(e) => setExpiry(e.target.value)}
        />
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          {t('sa.boss.customLimits')}
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {OVERRIDE_FIELDS.map((f) => (
            <div key={f.key} className="space-y-1">
              <Label className="text-xs">{t(f.labelKey)}</Label>
              <Input
                type="number"
                className="h-8 text-sm"
                placeholder={t('sa.boss.perPlan')}
                value={overrides[f.key]}
                onChange={(e) =>
                  setOverrides((o) => ({ ...o, [f.key]: e.target.value }))
                }
              />
            </div>
          ))}
        </div>
      </div>

      <Button size="sm" disabled={mut.isPending} onClick={() => mut.mutate()}>
        {mut.isPending ? t('sa.common.saving') : t('sa.boss.saveChanges')}
      </Button>
    </div>
  );
}

// --------------------------------------------------------------- Drawer

export function BossDrawer({ boss, onClose }: { boss: Boss; onClose: () => void }) {
  const t = useT();
  const overview = useQuery(bossOverviewQuery(boss.id));
  const [tab, setTab] = useState<TabKey>('overview');
  const [fullscreen, setFullscreen] = useState(false);
  const [width, setWidth] = useState(() => {
    const saved = localStorage.getItem('boss-drawer-w');
    return saved ? parseInt(saved, 10) : DEFAULT_W;
  });
  const dragging = useRef(false);

  const onDrag = useCallback((e: MouseEvent) => {
    if (!dragging.current) return;
    const w = Math.min(Math.max(window.innerWidth - e.clientX, MIN_W), window.innerWidth - 240);
    setWidth(w);
  }, []);

  useEffect(() => {
    const stop = () => {
      if (dragging.current) {
        dragging.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        setWidth((w) => {
          localStorage.setItem('boss-drawer-w', String(w));
          return w;
        });
      }
    };
    window.addEventListener('mousemove', onDrag);
    window.addEventListener('mouseup', stop);
    return () => {
      window.removeEventListener('mousemove', onDrag);
      window.removeEventListener('mouseup', stop);
    };
  }, [onDrag]);

  return (
    <>
      <motion.div
        className="fixed inset-0 z-30 bg-black/10"
        onClick={onClose}
        variants={drawerBackdrop}
        initial="hidden"
        animate="show"
        exit="exit"
      />

      <motion.aside
        className="fixed inset-y-0 right-0 z-40 bg-background border-l shadow-2xl flex flex-col"
        style={{ width: fullscreen ? '100vw' : width }}
        variants={drawerPanel}
        initial="hidden"
        animate="show"
        exit="exit"
      >
        {!fullscreen && (
          <div
            className="absolute inset-y-0 left-0 w-1.5 cursor-col-resize hover:bg-primary/30 transition-colors"
            onMouseDown={() => {
              dragging.current = true;
              document.body.style.cursor = 'col-resize';
              document.body.style.userSelect = 'none';
            }}
          />
        )}

        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b shrink-0">
          <div className="min-w-0">
            <p className="font-semibold truncate">{boss.name ?? boss.email}</p>
            <p className="text-xs text-muted-foreground font-mono truncate">{boss.email}</p>
          </div>
          {boss.plan_label && (
            <Badge variant="secondary" className="text-[10px]">
              {boss.plan_label}
            </Badge>
          )}
          <div className="ml-auto flex items-center gap-0.5">
            <button
              className="text-muted-foreground hover:text-foreground transition-colors p-1.5"
              onClick={() => setFullscreen((f) => !f)}
              aria-label={fullscreen ? t('sa.boss.minimize') : t('sa.boss.fullscreen')}
            >
              {fullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </button>
            <button
              className="text-muted-foreground hover:text-foreground transition-colors p-1.5"
              onClick={onClose}
              aria-label={t('sa.common.close')}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-5 pt-3 border-b shrink-0">
          {TABS.map((tabItem) => (
            <button
              key={tabItem.key}
              onClick={() => setTab(tabItem.key)}
              className={`px-3 pb-2 text-sm transition-colors border-b-2 -mb-px ${
                tab === tabItem.key
                  ? 'border-primary text-foreground font-medium'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {t(tabItem.labelKey)}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">
          <motion.div key={tab} variants={tabFade} initial="hidden" animate="show" className="h-full min-h-0">
            {tab === 'overview' &&
              (overview.isLoading || !overview.data ? (
                <Skeleton className="h-60 w-full" />
              ) : (
                <OverviewTab bossId={boss.id} data={overview.data} />
              ))}
            {tab === 'subscription' &&
              (overview.isLoading || !overview.data ? (
                <Skeleton className="h-60 w-full" />
              ) : (
                <SubscriptionTab key={boss.id} bossId={boss.id} data={overview.data} />
              ))}
            {tab === 'ai' && <BossAiTab bossId={boss.id} />}
            {tab === 'chat' && <BossChatTab bossId={boss.id} />}
          </motion.div>
        </div>
      </motion.aside>
    </>
  );
}
