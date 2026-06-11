import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ApiError } from '@/lib/api';
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
  const platformModels = tierModels.filter((m) => !m.is_own);
  const ownModels = tierModels.filter((m) => m.is_own);

  const dirty = selected !== (currentModelId?.toString() ?? '');

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <p className="text-sm font-semibold">{SLOT_LABELS[slot.slot]}</p>
      <Select
        value={selected || 'default'}
        onValueChange={(v) => setSelected(v === 'default' ? '' : v)}
      >
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="default">— mặc định nền tảng —</SelectItem>
          <SelectGroup>
            <SelectLabel>Model được cấp</SelectLabel>
            {platformModels.map((m) => (
              <SelectItem key={m.id} value={m.id.toString()}>
                {m.provider} / {m.name}
              </SelectItem>
            ))}
          </SelectGroup>
          {ownModels.length > 0 && (
            <SelectGroup>
              <SelectLabel>Model của bạn</SelectLabel>
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
    mutationFn: async () => {
      const test = await testAiKey({ provider, api_key: keyVal });
      if (!test.ok) throw new Error(test.message);
      return patchAiKey({ provider, api_key: keyVal });
    },
    onSuccess: () => {
      setKeyVal('');
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      toast.success(`Key ${PROVIDER_LABELS[provider]} hợp lệ — đã lưu.`);
    },
    onError: (e) =>
      toast.error(
        e instanceof Error && e.message && !e.message.startsWith('API ')
          ? `Không lưu key: ${e.message}`
          : 'Lưu key thất bại.'
      ),
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
        {saveMut.isPending ? 'Đang kiểm tra…' : 'Lưu'}
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

function OwnModelsSection({
  models,
  keysPresent,
}: {
  models: ModelOption[];
  keysPresent: Record<string, boolean>;
}) {
  const qc = useQueryClient();
  const ownModels = models.filter((m) => m.is_own);

  const [provider, setProvider] = useState<string>('groq');
  const [available, setAvailable] = useState<{ id: string }[]>([]);
  const [name, setName] = useState('');
  const [tier, setTier] = useState('smart');
  const [vision, setVision] = useState(false);
  const [loadingList, setLoadingList] = useState(false);

  const hasKey = keysPresent[provider];

  const loadModels = async () => {
    setLoadingList(true);
    try {
      const res = await listProviderModels(provider);
      if (!res.ok) {
        toast.error(res.message ?? 'Không tải được danh sách model.');
        setAvailable([]);
      } else {
        setAvailable(res.models);
        if (res.models.length === 0) toast.info('Provider không trả về model nào.');
      }
    } catch {
      toast.error('Không tải được danh sách model.');
    } finally {
      setLoadingList(false);
    }
  };

  const addMut = useMutation({
    mutationFn: () => addOwnModel({ provider, name: name.trim(), tier, vision }),
    onSuccess: () => {
      setName('');
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      toast.success('Đã thêm model của bạn.');
    },
    onError: (e) => {
      const detail =
        e instanceof ApiError && e.body && typeof e.body === 'object'
          ? (e.body as { detail?: string }).detail
          : undefined;
      toast.error(detail ?? 'Thêm model thất bại.');
    },
  });

  const delMut = useMutation({
    mutationFn: (id: number) => deleteOwnModel(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: aiQuery.queryKey });
      toast.success('Đã xoá model.');
    },
    onError: () => toast.error('Xoá model thất bại.'),
  });

  return (
    <section>
      <h2 className="text-sm font-semibold mb-1">Model của bạn</h2>
      <p className="text-xs text-muted-foreground mb-3">
        Thêm model bất kỳ của provider, chạy bằng API key của bạn. Cần lưu key provider tương ứng
        trước.
      </p>

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
                Xoá
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
                    {PROVIDER_LABELS[p]}
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
                    <SelectValue placeholder="Chọn model…" />
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
                onClick={loadModels}
              >
                {loadingList ? 'Đang tải…' : 'Tải danh sách'}
              </Button>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Dùng cho slot</Label>
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
            Hỗ trợ đọc ảnh (vision)
          </label>
          <Button
            size="sm"
            className="h-8 ml-auto"
            disabled={!name.trim() || addMut.isPending || !hasKey}
            onClick={() => addMut.mutate()}
          >
            {addMut.isPending ? 'Đang thêm…' : 'Thêm model'}
          </Button>
        </div>
        {!hasKey && (
          <p className="text-xs text-amber-600 dark:text-amber-500">
            Bạn cần lưu API key {PROVIDER_LABELS[provider]} ở mục trên trước khi thêm model riêng.
          </p>
        )}
      </div>
    </section>
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
