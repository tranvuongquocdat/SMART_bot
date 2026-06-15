import { useState, useEffect, type ReactNode } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { fadeUp, staggerContainer } from '@/lib/motion';
import { useT } from '@/lib/i18n';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  aiQuery,
  patchAiSlot,
  patchAiCap,
  patchAiKey,
  testAiKey,
  deleteOwnModel,
  type ModelOption,
  type SlotInfo,
} from './api';
import { OwnModelDrawer } from './own-model-drawer';

const SLOT_LABELS: Record<string, string> = {
  smart: 'aitab.slot.smart',
  fast: 'aitab.slot.fast',
  vision: 'aitab.slot.vision',
};

const PROVIDERS = ['openai', 'groq', 'gemini', 'custom'] as const;
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  groq: 'Groq',
  gemini: 'Gemini',
  custom: 'Custom / Self-hosted',
};

// Khung section nhất quán cho cả trang (card + tiêu đề + mô tả + animation).
function Section({
  title,
  desc,
  children,
}: {
  title: string;
  desc?: string;
  children: ReactNode;
}) {
  return (
    <motion.section
      variants={fadeUp}
      className="rounded-[14px] surface-section bg-card-grad p-5"
    >
      <h2 className="text-[13.5px] font-semibold tracking-tight">{title}</h2>
      {desc && <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>}
      <div className="mt-4">{children}</div>
    </motion.section>
  );
}

function SlotCard({
  slot,
  currentModelId,
  models,
  onSave,
  saving,
}: {
  slot: SlotInfo;
  currentModelId: number | null;
  models: ModelOption[];
  onSave: (modelId: number | null) => void;
  saving: boolean;
}) {
  const t = useT();
  const [selected, setSelected] = useState<string>(currentModelId?.toString() ?? '');

  useEffect(() => {
    setSelected(currentModelId?.toString() ?? '');
  }, [currentModelId]);

  const tierModels = slot.slot === 'vision'
    ? models.filter((m) => m.capabilities.includes('vision'))
    : models.filter((m) => m.tier === slot.slot);
  const platformModels = tierModels.filter((m) => !m.is_own);
  const ownModels = tierModels.filter((m) => m.is_own);

  const dirty = selected !== (currentModelId?.toString() ?? '');

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3 transition-all hover:border-[hsl(var(--border-strong))] hover:shadow-sm">
      <p className="text-sm font-semibold">{t(SLOT_LABELS[slot.slot])}</p>
      <Select
        value={selected || 'default'}
        onValueChange={(v) => setSelected(v === 'default' ? '' : v)}
      >
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="default">{t('aitab.platformDefault')}</SelectItem>
          <SelectGroup>
            <SelectLabel>{t('aitab.grantedModels')}</SelectLabel>
            {platformModels.map((m) => (
              <SelectItem key={m.id} value={m.id.toString()}>
                {m.provider} / {m.name}
              </SelectItem>
            ))}
          </SelectGroup>
          {ownModels.length > 0 && (
            <SelectGroup>
              <SelectLabel>{t('aitab.yourModels')}</SelectLabel>
              {ownModels.map((m) => (
                <SelectItem key={m.id} value={m.id.toString()}>
                  {m.provider} / {m.name}
                </SelectItem>
              ))}
            </SelectGroup>
          )}
        </SelectContent>
      </Select>
      {dirty && (
        <Button
          size="sm"
          disabled={saving}
          onClick={() => onSave(selected ? parseInt(selected, 10) : null)}
        >
          {saving ? t('common.saving') : t('aitab.saveSlot')}
        </Button>
      )}
    </div>
  );
}

function KeyRow({
  provider,
  present,
  last4,
  baseUrlSaved,
}: {
  provider: string;
  present: boolean;
  last4?: string;
  baseUrlSaved?: string;
}) {
  const t = useT();
  const qc = useQueryClient();
  const [keyVal, setKeyVal] = useState('');
  const isCustom = provider === 'custom';
  const [baseUrl, setBaseUrl] = useState(baseUrlSaved ?? '');

  useEffect(() => {
    setBaseUrl(baseUrlSaved ?? '');
  }, [baseUrlSaved]);

  const saveMut = useMutation({
    mutationFn: async () => {
      const test = await testAiKey({ provider, api_key: keyVal, base_url: isCustom ? baseUrl : undefined });
      if (!test.ok) throw new Error(test.message);
      return patchAiKey({ provider, api_key: keyVal, base_url: isCustom ? baseUrl : undefined });
    },
    onSuccess: () => {
      setKeyVal('');
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      toast.success(t('aitab.keySaved', { provider: PROVIDER_LABELS[provider] }));
    },
    onError: (e) =>
      toast.error(
        e instanceof Error && e.message && !e.message.startsWith('API ')
          ? t('aitab.keySaveErrorMsg', { msg: e.message })
          : t('aitab.keySaveError')
      ),
  });

  const clearMut = useMutation({
    mutationFn: () => patchAiKey({ provider, clear: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      toast.success(t('aitab.keyDeleted', { provider: PROVIDER_LABELS[provider] }));
    },
    onError: () => toast.error(t('aitab.keyDeleteError')),
  });

  const placeholder = present
    ? t('aitab.keyHasPlaceholder', { last4: last4 ?? '' })
    : provider === 'openai' ? 'sk-…' : provider === 'groq' ? 'gsk_…' : provider === 'gemini' ? 'AI…' : t('aitab.customKeyHint');

  // Custom / self-hosted: cần base_url + key → bố cục dọc trong khung riêng.
  if (isCustom) {
    const canSave = !!keyVal && !!baseUrl.trim() && !saveMut.isPending;
    return (
      <div className="rounded-lg border bg-card p-3 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase text-muted-foreground">
            {t('aitab.providerCustom')}
          </span>
          {present && (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs text-destructive hover:text-destructive"
              disabled={clearMut.isPending}
              onClick={() => clearMut.mutate()}
            >
              {t('common.delete')}
            </Button>
          )}
        </div>
        <Input
          className="h-8 text-sm"
          placeholder={t('aitab.baseUrlPlaceholder')}
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
        />
        <div className="flex gap-2">
          <Input
            type="password"
            className="h-8 text-sm flex-1"
            placeholder={placeholder}
            value={keyVal}
            onChange={(e) => setKeyVal(e.target.value)}
          />
          <Button
            size="sm"
            className="h-8 text-xs shrink-0"
            disabled={!canSave}
            onClick={() => saveMut.mutate()}
          >
            {saveMut.isPending ? t('aitab.checking') : t('common.save')}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-12 gap-2 items-center">
      <span className="col-span-2 text-xs font-semibold uppercase text-muted-foreground">
        {PROVIDER_LABELS[provider]}
      </span>
      <Input
        type="password"
        className="col-span-7 h-8 text-sm"
        placeholder={placeholder}
        value={keyVal}
        onChange={(e) => setKeyVal(e.target.value)}
      />
      <Button
        size="sm"
        variant="default"
        className="col-span-2 h-8 text-xs"
        disabled={!keyVal || saveMut.isPending}
        onClick={() => saveMut.mutate()}
      >
        {saveMut.isPending ? t('aitab.checking') : t('common.save')}
      </Button>
      {present && (
        <Button
          size="sm"
          variant="ghost"
          className="col-span-1 h-8 text-xs text-destructive hover:text-destructive"
          disabled={clearMut.isPending}
          onClick={() => clearMut.mutate()}
        >
          {t('common.delete')}
        </Button>
      )}
    </div>
  );
}

function ModelCard({
  m,
  onEdit,
  onDelete,
}: {
  m: ModelOption;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const t = useT();
  const hasCost = m.cost_per_1m_input_usd > 0 || m.cost_per_1m_output_usd > 0;
  return (
    <div className="rounded-lg border bg-card p-3 transition-all hover:border-[hsl(var(--border-strong))] hover:shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium text-sm truncate">{m.name}</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            {m.provider}
            <Badge variant="secondary" className="ml-1.5 text-[9px] uppercase">{m.tier}</Badge>
          </p>
        </div>
        <div className="flex items-center gap-0.5 shrink-0">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onEdit} aria-label={t('aitab.editModel')}>
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground hover:text-destructive"
            onClick={onDelete}
            aria-label={t('common.delete')}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
      {m.capabilities.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {m.capabilities.map((c) => (
            <span key={c} className="px-1.5 py-px rounded text-[10px] bg-muted text-muted-foreground">
              {c}
            </span>
          ))}
        </div>
      )}
      <p className="text-[11px] text-muted-foreground tabular-nums mt-2">
        {hasCost
          ? `$${m.cost_per_1m_input_usd}/1M in · $${m.cost_per_1m_output_usd}/1M out`
          : t('usage.byModel.noCost')}
      </p>
    </div>
  );
}

function OwnModelsSection({
  models,
  keysPresent,
}: {
  models: ModelOption[];
  keysPresent: Record<string, boolean>;
}) {
  const t = useT();
  const qc = useQueryClient();
  const ownModels = models.filter((m) => m.is_own);
  const [drawer, setDrawer] = useState<{ model: ModelOption | null } | null>(null);

  const delMut = useMutation({
    mutationFn: (id: number) => deleteOwnModel(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      toast.success(t('aitab.modelDeleted'));
    },
    onError: () => toast.error(t('aitab.modelDeleteError')),
  });

  return (
    <Section title={t('aitab.yourModels')} desc={t('aitab.yourModelsDesc')}>
      <div className="flex justify-end mb-3">
        <Button size="sm" onClick={() => setDrawer({ model: null })}>
          <Plus className="h-3.5 w-3.5 mr-1" />
          {t('aitab.addModel')}
        </Button>
      </div>

      {ownModels.length === 0 ? (
        <p className="text-sm text-muted-foreground py-2">{t('aitab.noOwnModels')}</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {ownModels.map((m) => (
            <ModelCard
              key={m.id}
              m={m}
              onEdit={() => setDrawer({ model: m })}
              onDelete={() => {
                if (confirm(t('aitab.deleteConfirm', { name: m.name }))) delMut.mutate(m.id);
              }}
            />
          ))}
        </div>
      )}

      <AnimatePresence>
        {drawer && (
          <OwnModelDrawer
            model={drawer.model}
            keysPresent={keysPresent}
            onClose={() => setDrawer(null)}
          />
        )}
      </AnimatePresence>
    </Section>
  );
}

export default function AiTab() {
  const t = useT();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery(aiQuery);

  const [cap, setCap] = useState('');

  useEffect(() => {
    if (data) setCap(data.cost_cap_usd_daily.toFixed(2));
  }, [data]);

  const slotMut = useMutation({
    mutationFn: ({ slot, model_id }: { slot: string; model_id: number | null }) =>
      patchAiSlot({ slot, model_id }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      toast.success(t('aitab.slotSaved'));
    },
    onError: () => toast.error(t('aitab.slotSaveError')),
  });

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

  return (
    <motion.div
      className="space-y-5 max-w-2xl"
      variants={staggerContainer(0.07)}
      initial="hidden"
      animate="show"
    >
      {/* 1 — Model cho từng việc (slots) */}
      <Section title={t('aitab.modelSlots')} desc={t('aitab.slotsDesc')}>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {data.slots.map((slot) => (
            <SlotCard
              key={slot.slot}
              slot={slot}
              currentModelId={slot.model_id}
              models={data.models}
              saving={slotMut.isPending}
              onSave={(model_id) => slotMut.mutate({ slot: slot.slot, model_id })}
            />
          ))}
        </div>
      </Section>

      {/* 2 — API key (BYO) */}
      <Section title={t('aitab.byoTitle')} desc={t('aitab.byoDesc')}>
        <div className="space-y-3">
          {PROVIDERS.map((prov) => {
            const info = data.keys[prov] ?? { present: false };
            return (
              <KeyRow
                key={prov}
                provider={prov}
                present={info.present}
                last4={info.last_4}
                baseUrlSaved={data.provider_urls?.[prov]}
              />
            );
          })}
        </div>
      </Section>

      {/* 3 — Model riêng (BYO) */}
      <OwnModelsSection
        models={data.models}
        keysPresent={Object.fromEntries(
          PROVIDERS.map((p) => [p, data.keys[p]?.present ?? false])
        )}
      />

      {/* 4 — Trần chi phí */}
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
          <Button
            size="sm"
            className="h-8"
            disabled={capMut.isPending}
            onClick={() => capMut.mutate()}
          >
            {capMut.isPending ? t('common.saving') : t('common.save')}
          </Button>
        </div>
      </Section>
    </motion.div>
  );
}
