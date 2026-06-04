import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { aiQuery, patchAiSlot, patchAiCap, patchAiKey, type ModelOption, type SlotInfo } from './api';

const SLOT_LABELS: Record<string, string> = {
  smart: 'Smart (suy luận sâu)',
  fast: 'Fast (phản hồi nhanh)',
  vision: 'Vision (đọc ảnh)',
};

const PROVIDERS = ['openai', 'groq', 'gemini'] as const;
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  groq: 'Groq',
  gemini: 'Gemini',
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
  const [selected, setSelected] = useState<string>(currentModelId?.toString() ?? '');

  useEffect(() => {
    setSelected(currentModelId?.toString() ?? '');
  }, [currentModelId]);

  const tierModels = slot.slot === 'vision'
    ? models.filter((m) => m.capabilities.includes('vision'))
    : models.filter((m) => m.tier === slot.slot);

  const dirty = selected !== (currentModelId?.toString() ?? '');

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <p className="text-sm font-semibold">{SLOT_LABELS[slot.slot]}</p>
      <select
        className="w-full rounded-md border bg-background px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
      >
        <option value="">— mặc định nền tảng —</option>
        {tierModels.map((m) => (
          <option key={m.id} value={m.id.toString()}>
            {m.provider} / {m.name}
          </option>
        ))}
      </select>
      {dirty && (
        <Button
          size="sm"
          disabled={saving}
          onClick={() => onSave(selected ? parseInt(selected, 10) : null)}
        >
          {saving ? 'Đang lưu…' : 'Lưu slot'}
        </Button>
      )}
    </div>
  );
}

function KeyRow({
  provider,
  present,
  last4,
}: {
  provider: string;
  present: boolean;
  last4?: string;
}) {
  const qc = useQueryClient();
  const [keyVal, setKeyVal] = useState('');

  const saveMut = useMutation({
    mutationFn: () => patchAiKey({ provider, api_key: keyVal }),
    onSuccess: () => {
      setKeyVal('');
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      toast.success(`Đã lưu key ${PROVIDER_LABELS[provider]}.`);
    },
    onError: () => toast.error('Lưu key thất bại.'),
  });

  const clearMut = useMutation({
    mutationFn: () => patchAiKey({ provider, clear: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      toast.success(`Đã xoá key ${PROVIDER_LABELS[provider]}.`);
    },
    onError: () => toast.error('Xoá key thất bại.'),
  });

  const placeholder = present
    ? `(đã có key — nhập để thay, **** ${last4 ?? ''})`
    : provider === 'openai' ? 'sk-…' : provider === 'groq' ? 'gsk_…' : 'AI…';

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
        Lưu
      </Button>
      {present && (
        <Button
          size="sm"
          variant="ghost"
          className="col-span-1 h-8 text-xs text-destructive hover:text-destructive"
          disabled={clearMut.isPending}
          onClick={() => clearMut.mutate()}
        >
          Xoá
        </Button>
      )}
    </div>
  );
}

export default function AiTab() {
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
      toast.success('Đã lưu model slot.');
    },
    onError: () => toast.error('Lưu slot thất bại.'),
  });

  const capMut = useMutation({
    mutationFn: () => patchAiCap({ cost_cap_usd_daily: parseFloat(cap) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      toast.success('Đã lưu cost cap.');
    },
    onError: () => toast.error('Lưu cost cap thất bại.'),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Đang tải…</p>;
  if (!data) return null;

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Model slots */}
      <section>
        <h2 className="text-sm font-semibold mb-3">Model slots</h2>
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
        <Label htmlFor="cost-cap">Cost cap (USD / ngày)</Label>
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
            {capMut.isPending ? 'Đang lưu…' : 'Lưu'}
          </Button>
        </div>
      </section>

      {/* BYO API keys */}
      <section>
        <h2 className="text-sm font-semibold mb-1">API key của bạn (BYO)</h2>
        <p className="text-xs text-muted-foreground mb-3">
          Nhập key để dùng quota của bạn thay vì quota nền tảng. Key được mã hoá (Fernet) trước khi lưu DB.
        </p>
        <div className="space-y-3">
          {PROVIDERS.map((prov) => {
            const info = data.keys[prov] ?? { present: false };
            return (
              <KeyRow
                key={prov}
                provider={prov}
                present={info.present}
                last4={info.last_4}
              />
            );
          })}
        </div>
      </section>
    </div>
  );
}
