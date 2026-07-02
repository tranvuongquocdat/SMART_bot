import { useState, useEffect, type ReactNode } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Pencil, Trash2, RefreshCw, Check, Info } from 'lucide-react';
import { toast } from 'sonner';
import { fadeUp, staggerContainer } from '@/lib/motion';
import { useT } from '@/lib/i18n';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  aiQuery,
  patchAiSlot,
  patchAiCap,
  checkAiKey,
  deleteOwnModel,
  type ModelOption,
  type AiSettings,
  type KeyStatus,
} from './api';
import { OwnModelDrawer } from './own-model-drawer';

// Khung section nhất quán cho cả trang (card + tiêu đề + mô tả + animation).
function Section({
  title,
  desc,
  action,
  children,
}: {
  title: string;
  desc?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <motion.section
      variants={fadeUp}
      className="rounded-[14px] surface-section bg-card-grad p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-[13.5px] font-semibold tracking-tight">{title}</h2>
          {desc && <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>}
        </div>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </motion.section>
  );
}

// Nút gán việc (Smart / Fast) — bật/tắt độc lập trên từng dòng. 1 model có thể
// nhận cả hai. Quy tắc 1-model-mỗi-việc do backend tự lo (gán = thay model cũ).
function JobToggle({
  kind,
  active,
  disabled,
  onClick,
}: {
  kind: 'smart' | 'fast';
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  const base =
    'inline-flex items-center gap-1 h-6 px-2.5 rounded-full text-[11.5px] font-semibold border transition-colors disabled:opacity-50';
  const off = 'border-border text-muted-foreground hover:bg-[hsl(var(--accent))]';
  const onSmart = 'bg-violet-500/15 border-violet-500/40 text-violet-300';
  const onFast = 'bg-primary/15 border-primary/40 text-primary';
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`${base} ${active ? (kind === 'smart' ? onSmart : onFast) : off}`}
    >
      {active && <Check className="h-3 w-3" />}
      {kind === 'smart' ? 'Smart' : 'Fast'}
    </button>
  );
}

// Trạng thái sống/chết của khoá provider, hiện ngay trên dòng (chỉ model "của bạn").
function KeyHealth({
  status,
  checking,
  onCheck,
}: {
  status?: KeyStatus;
  checking: boolean;
  onCheck: () => void;
}) {
  const t = useT();
  const dead = status?.ok === false;
  const ok = status?.ok === true;
  const dot = ok ? 'bg-primary' : dead ? 'bg-red-500' : 'bg-muted-foreground/50';
  const label = ok
    ? t('aitab.keyOk')
    : dead
      ? status?.message || t('aitab.keyDead')
      : t('aitab.keyUnchecked');
  return (
    <div className="flex items-center gap-1.5 mt-1 text-[10.5px]">
      <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${dot}`} />
      <span className={dead ? 'text-red-400 font-semibold' : 'text-muted-foreground'}>{label}</span>
      <button
        type="button"
        disabled={checking}
        onClick={onCheck}
        className="inline-flex items-center gap-1 text-primary font-semibold hover:underline disabled:opacity-50"
      >
        <RefreshCw className={`h-2.5 w-2.5 ${checking ? 'animate-spin' : ''}`} />
        {dead ? t('aitab.checkAgain') : t('aitab.checkKey')}
      </button>
    </div>
  );
}

function ModelRow({
  m,
  data,
  onEdit,
}: {
  m: ModelOption;
  data: AiSettings;
  onEdit: () => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const slotId = (slot: string) => data.slots.find((s) => s.slot === slot)?.model_id ?? null;
  const isSmart = slotId('smart') === m.id;
  const isFast = slotId('fast') === m.id;
  const keyInfo = m.is_own ? data.keys[m.provider] : undefined;

  const slotMut = useMutation({
    mutationFn: (b: { slot: string; model_id: number | null }) => patchAiSlot(b),
    onSuccess: () => qc.invalidateQueries({ queryKey: aiQuery.queryKey }),
    onError: () => toast.error(t('aitab.slotSaveError')),
  });

  const checkMut = useMutation({
    mutationFn: () => checkAiKey(m.provider),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      if (r.ok) toast.success(t('aitab.keyCheckOk', { provider: m.provider }));
      else toast.error(t('aitab.keyCheckDead', { provider: m.provider }));
    },
    onError: () => toast.error(t('aitab.keyCheckError')),
  });

  const delMut = useMutation({
    mutationFn: () => deleteOwnModel(m.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      toast.success(t('aitab.modelDeleted'));
    },
    onError: () => toast.error(t('aitab.modelDeleteError')),
  });

  const hasCost = m.cost_per_1m_input_usd > 0 || m.cost_per_1m_output_usd > 0;
  const idle = !isSmart && !isFast;

  return (
    <tr className={`border-b border-[hsl(var(--divider))] last:border-0 transition-colors hover:bg-[hsl(var(--accent))]/40 ${idle ? 'opacity-80' : ''}`}>
      {/* Model */}
      <td className="py-3 px-3 align-middle min-w-[190px]">
        <p className="font-semibold text-[13px]">{m.name}</p>
        <p className="text-[11px] text-muted-foreground mt-0.5">
          {m.provider}
          {' · '}
          <span className={`px-1.5 py-px rounded text-[9.5px] font-semibold ${m.is_own ? 'bg-amber-500/15 text-amber-400' : 'bg-muted text-muted-foreground'}`}>
            {m.is_own ? t('aitab.sourceOwn') : t('aitab.sourceGranted')}
          </span>
        </p>
        {m.is_own && (
          <KeyHealth
            status={keyInfo?.status}
            checking={checkMut.isPending}
            onCheck={() => checkMut.mutate()}
          />
        )}
      </td>
      {/* Dùng cho */}
      <td className="py-3 px-3 align-middle">
        <div className="flex gap-1.5">
          <JobToggle
            kind="smart"
            active={isSmart}
            disabled={slotMut.isPending}
            onClick={() => slotMut.mutate({ slot: 'smart', model_id: isSmart ? null : m.id })}
          />
          <JobToggle
            kind="fast"
            active={isFast}
            disabled={slotMut.isPending}
            onClick={() => slotMut.mutate({ slot: 'fast', model_id: isFast ? null : m.id })}
          />
        </div>
      </td>
      {/* Khả năng */}
      <td className="py-3 px-3 align-middle">
        <div className="flex flex-wrap gap-1 max-w-[200px]">
          {m.capabilities.length === 0 ? (
            <span className="text-[11px] text-muted-foreground">—</span>
          ) : (
            m.capabilities.map((c) => (
              <span
                key={c}
                className={`px-1.5 py-px rounded-full text-[10px] ${c === 'vision' ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'}`}
              >
                {c}
              </span>
            ))
          )}
        </div>
      </td>
      {/* Chi phí */}
      <td className="py-3 px-3 align-middle whitespace-nowrap">
        {hasCost ? (
          <span className="text-[12.5px] tabular-nums">
            ${m.cost_per_1m_input_usd}
            <span className="text-[10.5px] text-muted-foreground"> vào</span>
            {' · '}${m.cost_per_1m_output_usd}
            <span className="text-[10.5px] text-muted-foreground"> ra</span>
          </span>
        ) : (
          <span className="text-[11px] text-muted-foreground">{t('usage.byModel.noCost')}</span>
        )}
      </td>
      {/* Ngữ cảnh */}
      <td className="py-3 px-3 align-middle text-[12.5px] tabular-nums text-muted-foreground whitespace-nowrap">
        {m.ctx_max ? `${Math.round(m.ctx_max / 1000)}k` : '—'}
      </td>
      {/* Actions */}
      <td className="py-3 px-3 align-middle">
        <div className="flex gap-0.5 justify-end">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onEdit} aria-label={t('aitab.editModel')}>
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          {m.is_own && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-destructive"
              onClick={() => {
                if (confirm(t('aitab.deleteConfirm', { name: m.name }))) delMut.mutate();
              }}
              aria-label={t('common.delete')}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </td>
    </tr>
  );
}

export default function AiTab() {
  const t = useT();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery(aiQuery);

  const [cap, setCap] = useState('');
  const [drawer, setDrawer] = useState<{ model: ModelOption | null } | null>(null);

  useEffect(() => {
    if (data) setCap(data.cost_cap_usd_daily.toFixed(2));
  }, [data]);

  const capMut = useMutation({
    mutationFn: () => patchAiCap({ cost_cap_usd_daily: parseFloat(cap) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      toast.success(t('aitab.capSaved'));
    },
    onError: () => toast.error(t('aitab.capSaveError')),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">{t('common.loading')}</p>;
  if (!data) return null;

  // Thứ tự ổn định theo backend (provider · name) — bật/tắt việc KHÔNG đổi thứ tự.
  const models = data.models;

  return (
    <motion.div
      className="space-y-5 max-w-4xl"
      variants={staggerContainer(0.07)}
      initial="hidden"
      animate="show"
    >
      {/* 1 — Bảng model */}
      <Section
        title={t('aitab.modelsTitle')}
        desc={t('aitab.modelsSubtitle')}
        action={
          <Button size="sm" onClick={() => setDrawer({ model: null })}>
            <Plus className="h-3.5 w-3.5 mr-1" />
            {t('aitab.addModel')}
          </Button>
        }
      >
        {models.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">{t('aitab.emptyModels')}</p>
        ) : (
          <div className="overflow-x-auto -mx-1 px-1">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-[hsl(var(--divider))]">
                  {[
                    'aitab.colModel',
                    'aitab.colUsedFor',
                    'aitab.colCaps',
                    'aitab.colCost',
                    'aitab.colCtx',
                  ].map((k) => (
                    <th
                      key={k}
                      className="text-left text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground pb-2.5 px-3 whitespace-nowrap"
                    >
                      {t(k)}
                    </th>
                  ))}
                  <th />
                </tr>
              </thead>
              <tbody>
                {models.map((m) => (
                  <ModelRow key={m.id} m={m} data={data} onEdit={() => setDrawer({ model: m })} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-4 space-y-2.5">
          {/* Định nghĩa từng loại việc */}
          <div className="flex flex-col gap-1.5 text-[11.5px] text-muted-foreground">
            <span className="inline-flex items-start gap-1.5">
              <span className="inline-flex items-center h-5 px-2 rounded-full text-[10px] font-semibold bg-violet-500/15 text-violet-300 border border-violet-500/40 shrink-0">Smart</span>
              {t('aitab.defSmart')}
            </span>
            <span className="inline-flex items-start gap-1.5">
              <span className="inline-flex items-center h-5 px-2 rounded-full text-[10px] font-semibold bg-primary/15 text-primary border border-primary/40 shrink-0">Fast</span>
              {t('aitab.defFast')}
            </span>
            <span className="inline-flex items-start gap-1.5">
              <span className="inline-flex items-center h-5 px-2 rounded-full text-[10px] font-semibold bg-primary/10 text-primary shrink-0">vision</span>
              {t('aitab.defVision')}
            </span>
          </div>
          <p className="flex items-start gap-1.5 text-[11.5px] text-muted-foreground pt-1 border-t border-[hsl(var(--divider))]">
            <Info className="h-3.5 w-3.5 mt-1 text-muted-foreground shrink-0" />
            <span>{t('aitab.keyHealthHint')}</span>
          </p>
        </div>
      </Section>

      {/* 2 — Trần chi phí */}
      <Section title={t('aitab.costCap')} desc={t('aitab.costCapDesc')}>
        <div className="flex gap-2 max-w-xs">
          <Input
            id="cost-cap"
            type="number"
            step="0.01"
            min="0"
            value={cap}
            onChange={(e) => setCap(e.target.value)}
            className="w-32 h-8 text-sm"
          />
          <Button size="sm" className="h-8" disabled={capMut.isPending} onClick={() => capMut.mutate()}>
            {capMut.isPending ? t('common.saving') : t('common.save')}
          </Button>
        </div>
      </Section>

      <AnimatePresence>
        {drawer && (
          <OwnModelDrawer model={drawer.model} onClose={() => setDrawer(null)} />
        )}
      </AnimatePresence>
    </motion.div>
  );
}
