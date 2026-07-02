import { useEffect, useState, useCallback, type MouseEvent as ReactMouseEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Trash2, X, RefreshCw, Check, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { drawerBackdrop, drawerPanel } from '@/lib/motion';
import { ApiError } from '@/lib/api';
import { useT } from '@/lib/i18n';
import {
  aiQuery, addOwnModel, patchOwnModel, deleteOwnModel, listProviderModels,
  patchAiKey, checkAiKey, getModelMetadata,
  type ModelOption, type KeyInfo,
} from './api';

export const CAPS = ['text', 'vision', 'thinking', 'tools', 'audio'] as const;
const PROVIDERS = ['openai', 'groq', 'gemini', 'custom'] as const;
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI', groq: 'Groq', gemini: 'Gemini', custom: 'Custom / Self-hosted',
};

function CapToggles({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const toggle = (c: string) =>
    onChange(value.includes(c) ? value.filter((x) => x !== c) : [...value, c]);
  return (
    <div className="flex flex-wrap gap-1.5">
      {CAPS.map((c) => {
        const on = value.includes(c);
        return (
          <button
            key={c}
            type="button"
            onClick={() => toggle(c)}
            className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
              on
                ? 'bg-primary/15 border-primary/40 text-primary'
                : 'bg-transparent border-border text-muted-foreground hover:bg-[hsl(var(--hover))]'
            }`}
          >
            {c}
          </button>
        );
      })}
    </div>
  );
}

// Khối "Nhà cung cấp" — khoá theo provider (dùng chung mọi model cùng provider).
// Có: trạng thái sống/chết + Kiểm tra (khoá đã lưu) + Đổi khoá / nhập khoá mới.
function ProviderKeyBlock({
  provider,
  info,
  baseUrlSaved,
  sameProviderCount,
}: {
  provider: string;
  info?: KeyInfo;
  baseUrlSaved?: string;
  sameProviderCount: number;
}) {
  const t = useT();
  const qc = useQueryClient();
  const isCustom = provider === 'custom';
  // State khởi tạo từ props; reset khi đổi provider qua key={provider} ở call site
  // (tránh setState-trong-effect). Trong cùng provider, save thành công tự tắt editing.
  const present = info?.present ?? false;
  const [editing, setEditing] = useState(!present);
  const [keyVal, setKeyVal] = useState('');
  const [baseUrl, setBaseUrl] = useState(baseUrlSaved ?? '');

  const invalidate = () => qc.invalidateQueries({ queryKey: aiQuery.queryKey });

  const saveMut = useMutation({
    mutationFn: () =>
      patchAiKey({ provider, api_key: keyVal, base_url: isCustom ? baseUrl.trim() : undefined }),
    onSuccess: () => {
      invalidate();
      setKeyVal('');
      setEditing(false);
      toast.success(t('aitab.keySaved', { provider: PROVIDER_LABELS[provider] ?? provider }));
    },
    onError: (e) => {
      const detail = e instanceof ApiError && e.body && typeof e.body === 'object'
        ? (e.body as { detail?: string }).detail : undefined;
      toast.error(detail ?? t('aitab.keySaveError'));
    },
  });

  const checkMut = useMutation({
    mutationFn: () => checkAiKey(provider),
    onSuccess: (r) => {
      invalidate();
      if (r.ok) toast.success(t('aitab.keyCheckOk', { provider }));
      else toast.error(t('aitab.keyCheckDead', { provider }));
    },
    onError: () => toast.error(t('aitab.keyCheckError')),
  });

  const st = info?.status;
  const dot = st?.ok === true ? 'bg-primary' : st?.ok === false ? 'bg-red-500' : 'bg-muted-foreground/50';
  const statusLabel = st?.ok === true
    ? t('aitab.keyOk')
    : st?.ok === false
      ? (st.message || t('aitab.keyDead'))
      : t('aitab.keyUnchecked');
  const canSave = !!keyVal && (!isCustom || !!baseUrl.trim()) && !saveMut.isPending;

  return (
    <div className="rounded-[10px] border bg-background/40 p-3 space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
          {t('aitab.providerLabel')} · {PROVIDER_LABELS[provider] ?? provider}
        </span>
        {sameProviderCount > 1 && (
          <span className="text-[10.5px] text-muted-foreground">
            {t('aitab.keyShared', { count: sameProviderCount })}
          </span>
        )}
      </div>

      {!editing && present ? (
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-2 h-8 rounded-lg border bg-background px-2.5 text-[12.5px] tabular-nums flex-1 min-w-[150px]">
            <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
            <span className={st?.ok === false ? 'text-red-400 font-semibold' : ''}>{statusLabel}</span>
            {info?.last_4 && <span className="text-muted-foreground">· ••••{info.last_4}</span>}
          </div>
          <Button
            size="sm" variant="ghost" className="h-8 text-xs"
            disabled={checkMut.isPending}
            onClick={() => checkMut.mutate()}
          >
            <RefreshCw className={`h-3 w-3 mr-1 ${checkMut.isPending ? 'animate-spin' : ''}`} />
            {t('aitab.checkKey')}
          </Button>
          <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={() => setEditing(true)}>
            {t('aitab.changeKey')}
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          {isCustom && (
            <Input
              className="h-8 text-sm"
              placeholder={t('aitab.baseUrlPlaceholder')}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          )}
          <div className="flex gap-2">
            <Input
              type="password"
              className="h-8 text-sm flex-1"
              placeholder={present ? t('aitab.newKeyPlaceholder') : 'sk-…'}
              value={keyVal}
              onChange={(e) => setKeyVal(e.target.value)}
            />
            <Button
              size="sm" className="h-8 text-xs shrink-0"
              disabled={!canSave}
              onClick={() => saveMut.mutate()}
            >
              <Check className="h-3 w-3 mr-1" />
              {saveMut.isPending ? t('aitab.checking') : t('aitab.checkAndSave')}
            </Button>
            {present && (
              <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={() => { setEditing(false); setKeyVal(''); }}>
                {t('common.cancel')}
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function OwnModelDrawer({
  model,
  onClose,
}: {
  model: ModelOption | null; // null = add mode
  onClose: () => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const isEdit = model !== null;
  const { data: settings } = useQuery(aiQuery);

  const [provider, setProvider] = useState(model?.provider ?? 'groq');
  const [name, setName] = useState(model?.name ?? '');
  const [caps, setCaps] = useState<string[]>(model?.capabilities ?? []);
  const [costIn, setCostIn] = useState(model?.cost_per_1m_input_usd ? String(model.cost_per_1m_input_usd) : '');
  const [costOut, setCostOut] = useState(model?.cost_per_1m_output_usd ? String(model.cost_per_1m_output_usd) : '');
  const [available, setAvailable] = useState<{ id: string }[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [ctxMax, setCtxMax] = useState<number | null>(model?.ctx_max ?? null);
  const [metaLoading, setMetaLoading] = useState(false);

  // Tự điền khả năng + giá + ngữ cảnh qua LLM khi chọn/nhập model (giá là ước tính).
  const fetchMeta = async (mid: string) => {
    const id = mid.trim();
    if (!id) return;
    setMetaLoading(true);
    try {
      const r = await getModelMetadata(provider, id);
      if (r.ok) {
        if (r.capabilities?.length) setCaps(r.capabilities);
        if (r.cost_per_1m_input_usd != null) setCostIn(String(r.cost_per_1m_input_usd));
        if (r.cost_per_1m_output_usd != null) setCostOut(String(r.cost_per_1m_output_usd));
        if (r.ctx_max != null) setCtxMax(r.ctx_max);
        toast.success(t('aitab.autofillDone'));
      }
    } catch {
      /* im lặng — boss vẫn nhập tay được */
    } finally {
      setMetaLoading(false);
    }
  };

  const keyInfo = settings?.keys[provider];
  const hasKey = keyInfo?.present ?? false;
  const baseUrlSaved = settings?.provider_urls?.[provider];
  const sameProviderCount = (settings?.models ?? []).filter(
    (m) => m.is_own && m.provider === provider,
  ).length + (isEdit ? 0 : 1);
  const invalidate = () => qc.invalidateQueries({ queryKey: aiQuery.queryKey });

  const loadModels = useCallback(async () => {
    if (isEdit) return;
    setLoadingList(true);
    try {
      const res = await listProviderModels(provider);
      setAvailable(res.ok ? res.models : []);
    } catch {
      setAvailable([]);
    } finally {
      setLoadingList(false);
    }
  }, [provider, isEdit]);

  useEffect(() => {
    if (!isEdit && hasKey) void loadModels();
    else setAvailable([]);
  }, [provider, hasKey, isEdit, loadModels]);

  const saveMut = useMutation({
    mutationFn: () => {
      const ci = costIn.trim() ? Number(costIn) : null;
      const co = costOut.trim() ? Number(costOut) : null;
      if (isEdit) {
        return patchOwnModel(model!.id, {
          capabilities: caps, cost_per_1m_input_usd: ci, cost_per_1m_output_usd: co,
        });
      }
      return addOwnModel({
        provider, name: name.trim(), capabilities: caps,
        cost_per_1m_input_usd: ci, cost_per_1m_output_usd: co, ctx_max: ctxMax,
      });
    },
    onSuccess: () => {
      invalidate();
      toast.success(isEdit ? t('aitab.modelUpdated') : t('aitab.modelAdded'));
      onClose();
    },
    onError: (e) => {
      const detail = e instanceof ApiError && e.body && typeof e.body === 'object'
        ? (e.body as { detail?: string }).detail : undefined;
      toast.error(detail ?? (isEdit ? t('aitab.modelUpdateError') : t('aitab.modelAddError')));
    },
  });

  const delMut = useMutation({
    mutationFn: () => deleteOwnModel(model!.id),
    onSuccess: () => {
      invalidate();
      toast.success(t('aitab.modelDeleted'));
      onClose();
    },
    onError: () => toast.error(t('aitab.modelDeleteError')),
  });

  const canSave = isEdit ? !saveMut.isPending : !!name.trim() && hasKey && !saveMut.isPending;

  // Drawer kéo rộng được (mép trái), nhớ kích thước qua localStorage.
  const [width, setWidth] = useState(() => {
    const saved = Number(localStorage.getItem('aiDrawerWidth'));
    return saved >= 400 ? saved : 520;
  });
  const startResize = (e: ReactMouseEvent) => {
    e.preventDefault();
    let latest = width;
    const onMove = (ev: MouseEvent) => {
      latest = Math.min(Math.max(window.innerWidth - ev.clientX, 400), Math.round(window.innerWidth * 0.95));
      setWidth(latest);
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = '';
      localStorage.setItem('aiDrawerWidth', String(latest));
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    document.body.style.userSelect = 'none';
  };

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
        className="fixed inset-y-0 right-0 z-40 max-w-[95vw] bg-background border-l shadow-2xl flex flex-col"
        style={{ width }}
        variants={drawerPanel}
        initial="hidden"
        animate="show"
        exit="exit"
      >
        {/* Mép trái kéo để chỉnh rộng */}
        <div
          onMouseDown={startResize}
          className="absolute inset-y-0 left-0 w-1.5 z-50 cursor-col-resize hover:bg-primary/40 transition-colors"
          title={t('aitab.dragResize')}
        />
        <div className="flex items-center gap-3 px-5 py-3 border-b shrink-0">
          <div className="min-w-0">
            <p className="font-semibold truncate">
              {isEdit ? `${model!.provider} / ${model!.name}` : t('aitab.addModel')}
            </p>
            <p className="text-xs text-muted-foreground">
              {isEdit ? t('aitab.editModelHint') : t('aitab.addModelHint')}
            </p>
          </div>
          <button
            className="ml-auto text-muted-foreground hover:text-foreground transition-colors p-1.5"
            onClick={onClose}
            aria-label={t('common.cancel')}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {!isEdit && (
            <div className="space-y-1.5">
              <Label className="text-xs">{t('aitab.providerLabel')}</Label>
              <Select value={provider} onValueChange={(v) => { setProvider(v); setName(''); }}>
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
          )}

          {/* Khoá API của provider (dùng chung) — nhập / kiểm tra / đổi tại đây.
              key={provider}: đổi provider → remount để reset state từ props. */}
          <ProviderKeyBlock
            key={provider}
            provider={provider}
            info={keyInfo}
            baseUrlSaved={baseUrlSaved}
            sameProviderCount={sameProviderCount}
          />

          {!isEdit && (
            <div className="space-y-1.5">
              <Label className="text-xs">{t('aitab.model')}</Label>
              {available.length > 0 ? (
                <Select value={name || undefined} onValueChange={(v) => { setName(v); void fetchMeta(v); }}>
                  <SelectTrigger className="h-8 text-sm">
                    <SelectValue placeholder={loadingList ? t('common.loading') : t('aitab.chooseModel')} />
                  </SelectTrigger>
                  <SelectContent className="max-h-72">
                    {available.map((m) => (
                      <SelectItem key={m.id} value={m.id}>{m.id}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <div className="flex gap-2">
                  <Input
                    className="h-8 text-sm flex-1"
                    placeholder="vd: llama-3.3-70b-versatile"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    disabled={!hasKey}
                  />
                  <Button
                    type="button" size="sm" variant="ghost" className="h-8 text-xs shrink-0"
                    disabled={!hasKey || !name.trim() || metaLoading}
                    onClick={() => void fetchMeta(name)}
                  >
                    <Sparkles className={`h-3 w-3 mr-1 ${metaLoading ? 'animate-pulse' : ''}`} />
                    {t('aitab.autofill')}
                  </Button>
                </div>
              )}
              {!hasKey && (
                <p className="text-[11px] text-amber-600 dark:text-amber-500">
                  {t('aitab.needKeyFirst')}
                </p>
              )}
            </div>
          )}

          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <Label className="text-xs">{t('aitab.capabilities')}</Label>
              {metaLoading && (
                <span className="inline-flex items-center gap-1 text-[10.5px] text-primary">
                  <Sparkles className="h-3 w-3 animate-pulse" /> {t('aitab.autofilling')}
                </span>
              )}
            </div>
            <CapToggles value={caps} onChange={setCaps} />
            <p className="text-[11px] text-muted-foreground">{t('aitab.visionHint')}</p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">{t('aitab.costIn')}</Label>
              <Input
                type="number" min="0" step="0.01" className="h-8 text-sm" placeholder="—"
                value={costIn} onChange={(e) => setCostIn(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{t('aitab.costOut')}</Label>
              <Input
                type="number" min="0" step="0.01" className="h-8 text-sm" placeholder="—"
                value={costOut} onChange={(e) => setCostOut(e.target.value)}
              />
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground">{t('aitab.costHint')}</p>

          {isEdit && (
            <p className="text-[11px] text-muted-foreground">{t('aitab.assignJobHint')}</p>
          )}
        </div>

        <div className="flex items-center gap-2 px-5 py-3 border-t shrink-0">
          {isEdit && (
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive hover:text-destructive"
              disabled={delMut.isPending}
              onClick={() => delMut.mutate()}
            >
              <Trash2 className="h-3.5 w-3.5 mr-1" />
              {t('common.delete')}
            </Button>
          )}
          <Button size="sm" className="ml-auto" disabled={!canSave} onClick={() => saveMut.mutate()}>
            {saveMut.isPending ? t('common.saving') : isEdit ? t('common.save') : t('aitab.addModel')}
          </Button>
        </div>
      </motion.aside>
    </>
  );
}
