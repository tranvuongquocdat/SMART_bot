import { useState, useEffect, useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ApiError } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import {
  addBossOwnModel,
  bossAiQuery,
  deleteBossOwnModel,
  listBossProviderModels,
  patchBossAi,
  patchBossAiKey,
  type BossAiSettings,
} from './api';
import { useT } from '@/lib/i18n';

const SLOT_LABEL_KEYS: Record<string, string> = {
  smart: 'sa.boss.slotSmart',
  fast: 'sa.boss.slotFast',
  vision: 'sa.boss.slotVision',
};

const PROVIDERS = ['openai', 'groq', 'gemini', 'custom'] as const;
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  groq: 'Groq',
  gemini: 'Gemini',
  custom: 'Custom / Self-hosted',
};

function errDetail(e: unknown, fallback: string): string {
  if (e instanceof ApiError && e.body && typeof e.body === 'object') {
    const d = (e.body as { detail?: string }).detail;
    if (typeof d === 'string') return d;
  }
  return fallback;
}

function SlotRow({
  bossId,
  slot,
  modelId,
  models,
}: {
  bossId: number;
  slot: string;
  modelId: number | null;
  models: BossAiSettings['models'];
}) {
  const t = useT();
  const qc = useQueryClient();
  const tierModels =
    slot === 'vision'
      ? models.filter((m) => m.capabilities.includes('vision'))
      : models.filter((m) => m.tier === slot);
  const platform = tierModels.filter((m) => !m.is_own);
  const own = tierModels.filter((m) => m.is_own);

  const mut = useMutation({
    mutationFn: (newId: number | null) =>
      patchBossAi(bossId, { slot, model_id: newId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'boss', bossId, 'ai'] });
      toast.success(t('sa.boss.slotSaved'));
    },
    onError: (e) => toast.error(errDetail(e, t('sa.boss.slotSaveError'))),
  });

  return (
    <div className="flex items-center gap-3">
      <span className="text-sm w-44 shrink-0">{SLOT_LABEL_KEYS[slot] ? t(SLOT_LABEL_KEYS[slot]) : slot}</span>
      <Select
        value={modelId != null ? String(modelId) : 'default'}
        onValueChange={(v) => mut.mutate(v === 'default' ? null : Number(v))}
        disabled={mut.isPending}
      >
        <SelectTrigger className="h-8 text-sm flex-1">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="default">{t('sa.boss.platformDefault')}</SelectItem>
          <SelectGroup>
            <SelectLabel>{t('sa.boss.grantedModels')}</SelectLabel>
            {platform.map((m) => (
              <SelectItem key={m.id} value={String(m.id)}>
                {m.provider} / {m.name}
              </SelectItem>
            ))}
          </SelectGroup>
          {own.length > 0 && (
            <SelectGroup>
              <SelectLabel>{t('sa.boss.ownModels')}</SelectLabel>
              {own.map((m) => (
                <SelectItem key={m.id} value={String(m.id)}>
                  {m.provider} / {m.name}
                </SelectItem>
              ))}
            </SelectGroup>
          )}
        </SelectContent>
      </Select>
    </div>
  );
}

function KeyRow({
  bossId,
  provider,
  present,
  last4,
  baseUrlSaved,
}: {
  bossId: number;
  provider: string;
  present: boolean;
  last4?: string;
  baseUrlSaved?: string;
}) {
  const t = useT();
  const qc = useQueryClient();
  const [val, setVal] = useState('');
  const isCustom = provider === 'custom';
  const [baseUrl, setBaseUrl] = useState(baseUrlSaved ?? '');

  useEffect(() => {
    setBaseUrl(baseUrlSaved ?? '');
  }, [baseUrlSaved]);

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ['superadmin', 'boss', bossId, 'ai'] });

  const saveMut = useMutation({
    mutationFn: () =>
      patchBossAiKey(bossId, { provider, api_key: val, base_url: isCustom ? baseUrl : undefined }),
    onSuccess: () => {
      setVal('');
      invalidate();
      toast.success(t('sa.boss.keyValid', { provider: PROVIDER_LABELS[provider] }));
    },
    onError: (e) => toast.error(errDetail(e, t('sa.boss.keySaveError'))),
  });

  const clearMut = useMutation({
    mutationFn: () => patchBossAiKey(bossId, { provider, clear: true }),
    onSuccess: () => {
      invalidate();
      toast.success(t('sa.boss.keyDeleted', { provider: PROVIDER_LABELS[provider] }));
    },
    onError: () => toast.error(t('sa.boss.keyDeleteError')),
  });

  if (isCustom) {
    return (
      <div className="rounded-md border bg-card p-3 space-y-2">
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
              {t('sa.common.delete')}
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
            placeholder={present ? t('sa.boss.keyPresent', { last4: last4 ?? '' }) : t('aitab.customKeyHint')}
            value={val}
            onChange={(e) => setVal(e.target.value)}
          />
          <Button
            size="sm"
            className="h-8 text-xs shrink-0"
            disabled={!val || !baseUrl.trim() || saveMut.isPending}
            onClick={() => saveMut.mutate()}
          >
            {saveMut.isPending ? t('sa.boss.keyChecking') : t('sa.common.save')}
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
        placeholder={present ? t('sa.boss.keyPresent', { last4: last4 ?? '' }) : t('sa.boss.keyPlaceholder')}
        value={val}
        onChange={(e) => setVal(e.target.value)}
      />
      <Button
        size="sm"
        className="col-span-2 h-8 text-xs"
        disabled={!val || saveMut.isPending}
        onClick={() => saveMut.mutate()}
      >
        {saveMut.isPending ? t('sa.boss.keyChecking') : t('sa.common.save')}
      </Button>
      {present && (
        <Button
          size="sm"
          variant="ghost"
          className="col-span-1 h-8 text-xs text-destructive hover:text-destructive"
          disabled={clearMut.isPending}
          onClick={() => clearMut.mutate()}
        >
          {t('sa.common.delete')}
        </Button>
      )}
    </div>
  );
}

function OwnModels({ bossId, data }: { bossId: number; data: BossAiSettings }) {
  const t = useT();
  const qc = useQueryClient();
  const own = data.models.filter((m) => m.is_own);

  const [provider, setProvider] = useState('groq');
  const [available, setAvailable] = useState<{ id: string }[]>([]);
  const [name, setName] = useState('');
  const [tier, setTier] = useState('smart');
  const [costIn, setCostIn] = useState('');
  const [costOut, setCostOut] = useState('');
  const [loading, setLoading] = useState(false);

  const hasKey = data.keys[provider]?.present ?? false;

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ['superadmin', 'boss', bossId, 'ai'] });

  const load = useCallback(
    async (opts?: { silent?: boolean }) => {
      setLoading(true);
      try {
        const res = await listBossProviderModels(bossId, provider);
        if (!res.ok && !opts?.silent) toast.error(res.message ?? t('sa.boss.loadListFail'));
        setAvailable(res.ok ? res.models : []);
      } catch {
        if (!opts?.silent) toast.error(t('sa.boss.loadModelsFail'));
      } finally {
        setLoading(false);
      }
    },
    [bossId, provider, t],
  );

  // Tự tải danh sách model khi chọn provider (nếu boss đã có key).
  useEffect(() => {
    if (hasKey) {
      void load({ silent: true });
    } else {
      setAvailable([]);
    }
  }, [provider, hasKey, load]);

  const addMut = useMutation({
    mutationFn: () =>
      addBossOwnModel(bossId, {
        provider,
        name: name.trim(),
        tier,
        cost_per_1m_input_usd: costIn.trim() ? Number(costIn) : null,
        cost_per_1m_output_usd: costOut.trim() ? Number(costOut) : null,
      }),
    onSuccess: () => {
      setName('');
      setCostIn('');
      setCostOut('');
      invalidate();
      toast.success(t('sa.boss.modelAdded'));
    },
    onError: (e) => toast.error(errDetail(e, t('sa.boss.modelAddError'))),
  });

  const delMut = useMutation({
    mutationFn: (id: number) => deleteBossOwnModel(bossId, id),
    onSuccess: () => {
      invalidate();
      toast.success(t('sa.boss.modelDeleted'));
    },
    onError: () => toast.error(t('sa.common.deleteError')),
  });

  return (
    <section className="space-y-3">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        {t('sa.boss.ownModelsTitle')}
      </p>
      {own.length > 0 && (
        <ul className="space-y-2">
          {own.map((m) => (
            <li
              key={m.id}
              className="flex items-center justify-between rounded-md border bg-card px-3 py-2"
            >
              <span className="text-sm">
                {m.provider} / {m.name}
                <Badge variant="secondary" className="ml-2 text-[10px] uppercase">
                  {m.tier}
                </Badge>
              </span>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-destructive hover:text-destructive"
                disabled={delMut.isPending}
                onClick={() => delMut.mutate(m.id)}
              >
                {t('sa.common.delete')}
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div className="rounded-lg border bg-card p-3 space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label className="text-xs">Provider</Label>
            <Select
              value={provider}
              onValueChange={(v) => {
                setProvider(v);
                setAvailable([]);
                setName('');
              }}
            >
              <SelectTrigger className="h-8 text-sm w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROVIDERS.map((p) => (
                  <SelectItem key={p} value={p}>
                    {p === 'custom' ? t('aitab.providerCustom') : PROVIDER_LABELS[p]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1 flex-1 min-w-[180px]">
            <Label className="text-xs">Model</Label>
            {available.length > 0 ? (
              <Select value={name || undefined} onValueChange={setName}>
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue placeholder={t('sa.boss.chooseModel')} />
                </SelectTrigger>
                <SelectContent className="max-h-72">
                  {available.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input
                className="h-8 text-sm"
                placeholder={t('sa.boss.modelNamePlaceholder')}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            )}
          </div>
          <Button size="sm" variant="outline" className="h-8 text-xs" disabled={loading} onClick={() => load()}>
            {loading ? t('sa.common.loading') : t('sa.boss.loadList')}
          </Button>
          <div className="space-y-1">
            <Label className="text-xs">Slot</Label>
            <Select value={tier} onValueChange={setTier}>
              <SelectTrigger className="h-8 text-sm w-24">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="smart">Smart</SelectItem>
                <SelectItem value="fast">Fast</SelectItem>
                <SelectItem value="vision">Vision</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t('aitab.costIn')}</Label>
            <Input
              type="number" min="0" step="0.01"
              className="h-8 text-sm w-24"
              placeholder="—"
              value={costIn}
              onChange={(e) => setCostIn(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{t('aitab.costOut')}</Label>
            <Input
              type="number" min="0" step="0.01"
              className="h-8 text-sm w-24"
              placeholder="—"
              value={costOut}
              onChange={(e) => setCostOut(e.target.value)}
            />
          </div>
          <Button
            size="sm"
            className="h-8"
            disabled={!name.trim() || !hasKey || addMut.isPending}
            onClick={() => addMut.mutate()}
          >
            {t('sa.boss.add')}
          </Button>
        </div>
        {!hasKey && (
          <p className="text-xs text-amber-600 dark:text-amber-500">
            {t('sa.boss.noKeyWarn', { provider: PROVIDER_LABELS[provider] })}
          </p>
        )}
      </div>
    </section>
  );
}

export function BossAiTab({ bossId }: { bossId: number }) {
  const t = useT();
  const qc = useQueryClient();
  const ai = useQuery(bossAiQuery(bossId));
  const [cap, setCap] = useState<string | null>(null);

  const capMut = useMutation({
    mutationFn: (v: number) => patchBossAi(bossId, { cost_cap_usd_daily: v }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'boss', bossId] });
      toast.success(t('sa.boss.capSaved'));
    },
    onError: () => toast.error(t('sa.boss.capSaveError')),
  });

  if (ai.isLoading || !ai.data) return <Skeleton className="h-60 w-full" />;
  const data = ai.data;
  const capVal = cap ?? data.cost_cap_usd_daily.toFixed(2);

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          Model slots
        </p>
        {data.slots.map((s) => (
          <SlotRow
            key={s.slot}
            bossId={bossId}
            slot={s.slot}
            modelId={s.model_id}
            models={data.models}
          />
        ))}
      </section>

      <section className="space-y-2">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          {t('sa.boss.costCapTitle')}
        </p>
        <div className="flex gap-2">
          <Input
            type="number"
            step="0.01"
            min="0"
            className="h-8 text-sm w-28"
            value={capVal}
            onChange={(e) => setCap(e.target.value)}
          />
          <Button
            size="sm"
            className="h-8"
            disabled={capMut.isPending}
            onClick={() => capMut.mutate(parseFloat(capVal))}
          >
            {t('sa.common.save')}
          </Button>
        </div>
      </section>

      <section className="space-y-3">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          {t('sa.boss.apiKeysTitle')}
        </p>
        {PROVIDERS.map((p) => {
          const info = data.keys[p] ?? { present: false };
          return (
            <KeyRow
              key={p}
              bossId={bossId}
              provider={p}
              present={info.present}
              last4={info.last_4}
              baseUrlSaved={data.provider_urls?.[p]}
            />
          );
        })}
      </section>

      <OwnModels bossId={bossId} data={data} />
    </div>
  );
}
