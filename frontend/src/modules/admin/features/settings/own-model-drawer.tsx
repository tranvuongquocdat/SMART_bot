import { useEffect, useState, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Trash2, X } from 'lucide-react';
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
  type ModelOption,
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

export function OwnModelDrawer({
  model,
  keysPresent,
  onClose,
}: {
  model: ModelOption | null; // null = add mode
  keysPresent: Record<string, boolean>;
  onClose: () => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const isEdit = model !== null;

  const [provider, setProvider] = useState(model?.provider ?? 'groq');
  const [name, setName] = useState(model?.name ?? '');
  const [tier, setTier] = useState(model?.tier ?? 'smart');
  const [caps, setCaps] = useState<string[]>(model?.capabilities ?? []);
  const [costIn, setCostIn] = useState(model?.cost_per_1m_input_usd ? String(model.cost_per_1m_input_usd) : '');
  const [costOut, setCostOut] = useState(model?.cost_per_1m_output_usd ? String(model.cost_per_1m_output_usd) : '');
  const [available, setAvailable] = useState<{ id: string }[]>([]);
  const [loadingList, setLoadingList] = useState(false);

  const hasKey = keysPresent[provider] ?? false;
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
          tier, capabilities: caps, cost_per_1m_input_usd: ci, cost_per_1m_output_usd: co,
        });
      }
      return addOwnModel({
        provider, name: name.trim(), tier, capabilities: caps,
        cost_per_1m_input_usd: ci, cost_per_1m_output_usd: co,
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
        className="fixed inset-y-0 right-0 z-40 w-[440px] max-w-[92vw] bg-background border-l shadow-2xl flex flex-col"
        variants={drawerPanel}
        initial="hidden"
        animate="show"
        exit="exit"
      >
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
            <>
              <div className="space-y-1.5">
                <Label className="text-xs">Provider</Label>
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
                {!hasKey && (
                  <p className="text-[11px] text-amber-600 dark:text-amber-500">
                    {t('aitab.needKey', { provider: PROVIDER_LABELS[provider] ?? provider })}
                  </p>
                )}
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Model</Label>
                {available.length > 0 ? (
                  <Select value={name || undefined} onValueChange={setName}>
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
                  <Input
                    className="h-8 text-sm"
                    placeholder="vd: llama-3.3-70b-versatile"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                )}
              </div>
            </>
          )}

          <div className="space-y-1.5">
            <Label className="text-xs">{t('aitab.useForSlot')}</Label>
            <Select value={tier} onValueChange={setTier}>
              <SelectTrigger className="h-8 text-sm w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="smart">Smart</SelectItem>
                <SelectItem value="fast">Fast</SelectItem>
                <SelectItem value="vision">Vision</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">{t('aitab.capabilities')}</Label>
            <CapToggles value={caps} onChange={setCaps} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">{t('aitab.costIn')}</Label>
              <Input
                type="number" min="0" step="0.01"
                className="h-8 text-sm"
                placeholder="—"
                value={costIn}
                onChange={(e) => setCostIn(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{t('aitab.costOut')}</Label>
              <Input
                type="number" min="0" step="0.01"
                className="h-8 text-sm"
                placeholder="—"
                value={costOut}
                onChange={(e) => setCostOut(e.target.value)}
              />
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground">{t('aitab.costHint')}</p>
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
          <Button
            size="sm"
            className="ml-auto"
            disabled={!canSave}
            onClick={() => saveMut.mutate()}
          >
            {saveMut.isPending ? t('common.saving') : t('common.save')}
          </Button>
        </div>
      </motion.aside>
    </>
  );
}
