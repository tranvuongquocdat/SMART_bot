import { useState, useEffect, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ApiError } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
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
  listProviderModels,
  addOwnModel,
  deleteOwnModel,
  type ModelOption,
  type SlotInfo,
} from './api';

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
    <div className="rounded-lg border bg-card p-4 space-y-3">
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

  const [provider, setProvider] = useState<string>('groq');
  const [available, setAvailable] = useState<{ id: string }[]>([]);
  const [name, setName] = useState('');
  const [tier, setTier] = useState('smart');
  const [vision, setVision] = useState(false);
  const [loadingList, setLoadingList] = useState(false);

  const hasKey = keysPresent[provider];

  const loadModels = useCallback(
    async (opts?: { silent?: boolean }) => {
      setLoadingList(true);
      try {
        const res = await listProviderModels(provider);
        if (!res.ok) {
          if (!opts?.silent) toast.error(res.message ?? t('aitab.loadModelsError'));
          setAvailable([]);
        } else {
          setAvailable(res.models);
          if (res.models.length === 0 && !opts?.silent) toast.info(t('aitab.noProviderModels'));
        }
      } catch {
        if (!opts?.silent) toast.error(t('aitab.loadModelsError'));
      } finally {
        setLoadingList(false);
      }
    },
    [provider, t],
  );

  // Tự tải danh sách model ngay khi chọn provider (nếu đã có key) — không cần bấm.
  useEffect(() => {
    if (hasKey) {
      void loadModels({ silent: true });
    } else {
      setAvailable([]);
    }
  }, [provider, hasKey, loadModels]);

  const addMut = useMutation({
    mutationFn: () => addOwnModel({ provider, name: name.trim(), tier, vision }),
    onSuccess: () => {
      setName('');
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      toast.success(t('aitab.modelAdded'));
    },
    onError: (e) => {
      const detail =
        e instanceof ApiError && e.body && typeof e.body === 'object'
          ? (e.body as { detail?: string }).detail
          : undefined;
      toast.error(detail ?? t('aitab.modelAddError'));
    },
  });

  const delMut = useMutation({
    mutationFn: (id: number) => deleteOwnModel(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      toast.success(t('aitab.modelDeleted'));
    },
    onError: () => toast.error(t('aitab.modelDeleteError')),
  });

  return (
    <section>
      <h2 className="text-sm font-semibold mb-1">{t('aitab.yourModels')}</h2>
      <p className="text-xs text-muted-foreground mb-3">{t('aitab.yourModelsDesc')}</p>

      {ownModels.length > 0 && (
        <ul className="mb-4 space-y-2">
          {ownModels.map((m) => (
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
                {t('common.delete')}
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div className="rounded-lg border bg-card p-4 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <Label className="text-xs">Provider</Label>
            <Select
              value={provider}
              onValueChange={(v) => {
                setProvider(v);
                setAvailable([]);
                setName('');
              }}
            >
              <SelectTrigger className="h-8 text-sm">
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
          <div className="space-y-1.5 sm:col-span-2">
            <Label className="text-xs">Model</Label>
            <div className="flex gap-2">
              {available.length > 0 ? (
                <Select value={name || undefined} onValueChange={setName}>
                  <SelectTrigger className="h-8 text-sm flex-1">
                    <SelectValue placeholder={t('aitab.chooseModel')} />
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
                  className="h-8 text-sm flex-1"
                  placeholder="vd: llama-3.3-70b-versatile"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              )}
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-xs shrink-0"
                disabled={loadingList}
                onClick={() => loadModels()}
              >
                {loadingList ? t('common.loading') : t('aitab.loadList')}
              </Button>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-4">
          <div className="space-y-1.5">
            <Label className="text-xs">{t('aitab.useForSlot')}</Label>
            <Select value={tier} onValueChange={setTier}>
              <SelectTrigger className="h-8 text-sm w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="smart">Smart</SelectItem>
                <SelectItem value="fast">Fast</SelectItem>
                <SelectItem value="vision">Vision</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <label className="flex items-center gap-2 pb-1.5 text-xs text-muted-foreground">
            <Checkbox checked={vision} onCheckedChange={(v) => setVision(v === true)} />
            {t('aitab.visionSupport')}
          </label>
          <Button
            size="sm"
            className="h-8 ml-auto"
            disabled={!name.trim() || addMut.isPending || !hasKey}
            onClick={() => addMut.mutate()}
          >
            {addMut.isPending ? t('aitab.adding') : t('aitab.addModel')}
          </Button>
        </div>
        {!hasKey && (
          <p className="text-xs text-amber-600 dark:text-amber-500">
            {t('aitab.needKey', { provider: PROVIDER_LABELS[provider] })}
          </p>
        )}
      </div>
    </section>
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
    <div className="space-y-6 max-w-2xl">
      {/* Model slots */}
      <section>
        <h2 className="text-sm font-semibold mb-3">{t('aitab.modelSlots')}</h2>
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
      </section>

      {/* Cost cap */}
      <section className="space-y-2 max-w-xs">
        <Label htmlFor="cost-cap">{t('aitab.costCap')}</Label>
        <div className="flex gap-2">
          <Input
            id="cost-cap"
            type="number"
            step="0.01"
            min="0"
            value={cap}
            onChange={(e) => setCap(e.target.value)}
            className="w-32"
          />
          <Button
            size="sm"
            disabled={capMut.isPending}
            onClick={() => capMut.mutate()}
          >
            {capMut.isPending ? t('common.saving') : t('common.save')}
          </Button>
        </div>
      </section>

      {/* BYO API keys */}
      <section>
        <h2 className="text-sm font-semibold mb-1">{t('aitab.byoTitle')}</h2>
        <p className="text-xs text-muted-foreground mb-3">{t('aitab.byoDesc')}</p>
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
      </section>

      {/* Own (BYO) models */}
      <OwnModelsSection
        models={data.models}
        keysPresent={Object.fromEntries(
          PROVIDERS.map((p) => [p, data.keys[p]?.present ?? false])
        )}
      />
    </div>
  );
}
