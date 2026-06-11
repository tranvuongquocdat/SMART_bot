import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/data-table';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  modelsQuery,
  createModel,
  patchModel,
  deleteModel,
} from './api';
import type { Model } from './api';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

const TIER_LABELS: Record<string, string> = {
  smart: 'Smart',
  fast: 'Fast',
  vision: 'Vision',
};

// ---------------------------------------------------------------------------
// Add dialog
// ---------------------------------------------------------------------------

function AddModelDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    name: '',
    provider: '',
    tier: 'smart',
    endpoint_kind: 'openai_chat',
    ctx_max: 8000,
    cost_per_1m_input_usd: '',
    cost_per_1m_output_usd: '',
    is_platform_default: false,
    is_active: true,
    notes: '',
  });

  const mutation = useMutation({
    mutationFn: () => createModel({
      name: form.name.trim(),
      provider: form.provider.trim(),
      tier: form.tier,
      endpoint_kind: form.endpoint_kind,
      ctx_max: Number(form.ctx_max),
      cost_per_1m_input_usd: form.cost_per_1m_input_usd ? Number(form.cost_per_1m_input_usd) : null,
      cost_per_1m_output_usd: form.cost_per_1m_output_usd ? Number(form.cost_per_1m_output_usd) : null,
      is_platform_default: form.is_platform_default,
      is_active: form.is_active,
      notes: form.notes.trim() || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'models'] });
      toast.success('Đã thêm model');
      onOpenChange(false);
    },
    onError: () => toast.error('Thêm model thất bại'),
  });

  const set = (k: keyof typeof form, v: unknown) =>
    setForm(f => ({ ...f, [k]: v }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Thêm model mới</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3 mt-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Tên model</Label>
              <Input value={form.name} onChange={e => set('name', e.target.value)} placeholder="gpt-4o-mini" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Provider</Label>
              <Input value={form.provider} onChange={e => set('provider', e.target.value)} placeholder="openai" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Tier</Label>
              <Select value={form.tier} onValueChange={v => set('tier', v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="smart">smart</SelectItem>
                  <SelectItem value="fast">fast</SelectItem>
                  <SelectItem value="vision">vision</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Endpoint kind</Label>
              <Select value={form.endpoint_kind} onValueChange={v => set('endpoint_kind', v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="openai_chat">openai_chat</SelectItem>
                  <SelectItem value="google_gemini">google_gemini</SelectItem>
                  <SelectItem value="groq_chat">groq_chat</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Ctx max</Label>
              <Input
                type="number"
                value={form.ctx_max}
                onChange={e => set('ctx_max', Number(e.target.value))}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Cost/1M in</Label>
              <Input
                type="number"
                step="0.0001"
                value={form.cost_per_1m_input_usd}
                onChange={e => set('cost_per_1m_input_usd', e.target.value)}
                placeholder="0.15"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Cost/1M out</Label>
              <Input
                type="number"
                step="0.0001"
                value={form.cost_per_1m_output_usd}
                onChange={e => set('cost_per_1m_output_usd', e.target.value)}
                placeholder="0.60"
              />
            </div>
          </div>
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_platform_default}
                onChange={e => set('is_platform_default', e.target.checked)}
              />
              Platform default
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={e => set('is_active', e.target.checked)}
              />
              Active
            </label>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Notes</Label>
            <Input value={form.notes} onChange={e => set('notes', e.target.value)} placeholder="Ghi chú tùy chọn" />
          </div>
        </div>
        <DialogFooter className="mt-4">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Huỷ</Button>
          <Button
            disabled={!form.name.trim() || !form.provider.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            Thêm
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Edit dialog
// ---------------------------------------------------------------------------

function EditModelDialog({
  model,
  open,
  onOpenChange,
}: {
  model: Model;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    tier: model.tier,
    ctx_max: model.ctx_max,
    cost_per_1m_input_usd: model.cost_per_1m_input_usd?.toString() ?? '',
    cost_per_1m_output_usd: model.cost_per_1m_output_usd?.toString() ?? '',
    is_platform_default: model.is_platform_default,
    is_active: model.is_active,
    notes: model.notes ?? '',
  });

  const mutation = useMutation({
    mutationFn: () => patchModel(model.id, {
      tier: form.tier,
      ctx_max: Number(form.ctx_max),
      cost_per_1m_input_usd: form.cost_per_1m_input_usd ? Number(form.cost_per_1m_input_usd) : null,
      cost_per_1m_output_usd: form.cost_per_1m_output_usd ? Number(form.cost_per_1m_output_usd) : null,
      is_platform_default: form.is_platform_default,
      is_active: form.is_active,
      notes: form.notes.trim() || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'models'] });
      qc.invalidateQueries({ queryKey: ['superadmin', 'model-slots'] });
      toast.success('Đã cập nhật model');
      onOpenChange(false);
    },
    onError: () => toast.error('Cập nhật thất bại'),
  });

  const set = (k: keyof typeof form, v: unknown) =>
    setForm(f => ({ ...f, [k]: v }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Sửa model — {model.name}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3 mt-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Tier</Label>
              <Select value={form.tier} onValueChange={v => set('tier', v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="smart">smart</SelectItem>
                  <SelectItem value="fast">fast</SelectItem>
                  <SelectItem value="vision">vision</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Ctx max</Label>
              <Input
                type="number"
                value={form.ctx_max}
                onChange={e => set('ctx_max', Number(e.target.value))}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Cost/1M input (USD)</Label>
              <Input
                type="number"
                step="0.0001"
                value={form.cost_per_1m_input_usd}
                onChange={e => set('cost_per_1m_input_usd', e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Cost/1M output (USD)</Label>
              <Input
                type="number"
                step="0.0001"
                value={form.cost_per_1m_output_usd}
                onChange={e => set('cost_per_1m_output_usd', e.target.value)}
              />
            </div>
          </div>
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_platform_default}
                onChange={e => set('is_platform_default', e.target.checked)}
              />
              Platform default
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={e => set('is_active', e.target.checked)}
              />
              Active
            </label>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Notes</Label>
            <Input value={form.notes} onChange={e => set('notes', e.target.value)} />
          </div>
        </div>
        <DialogFooter className="mt-4">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Huỷ</Button>
          <Button disabled={mutation.isPending} onClick={() => mutation.mutate()}>Lưu</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Models tab
// ---------------------------------------------------------------------------

export function ModelsTab() {
  const qc = useQueryClient();
  const models = useQuery(modelsQuery);
  const [addOpen, setAddOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Model | null>(null);

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteModel(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'models'] });
      qc.invalidateQueries({ queryKey: ['superadmin', 'model-slots'] });
      toast.success('Đã xoá model');
    },
    onError: () => toast.error('Xoá thất bại'),
  });

  const columns: ColumnDef<Model>[] = [
    {
      header: 'Model',
      accessorKey: 'name',
      cell: ({ row }) => (
        <div>
          <div className="font-medium tracking-tight flex items-center gap-1.5">
            {row.original.name}
            {row.original.owner_boss_id != null && (
              <Badge variant="outline" className="text-[10px]">BYO boss #{row.original.owner_boss_id}</Badge>
            )}
          </div>
          <div className="text-xs text-muted-foreground font-mono">{row.original.provider}</div>
        </div>
      ),
    },
    {
      header: 'Tier',
      accessorKey: 'tier',
      cell: ({ row }) => (
        <Badge variant="outline" className="capitalize">
          {TIER_LABELS[row.original.tier] ?? row.original.tier}
        </Badge>
      ),
    },
    {
      header: 'Ctx',
      accessorKey: 'ctx_max',
      cell: ({ row }) => (
        <span className="text-xs font-mono">{row.original.ctx_max.toLocaleString()}</span>
      ),
    },
    {
      header: 'Cost/1M',
      cell: ({ row }) => {
        const { cost_per_1m_input_usd: inp, cost_per_1m_output_usd: out } = row.original;
        if (!inp && !out) return <span className="text-muted-foreground">—</span>;
        return (
          <div className="text-xs">
            <div>in: ${inp ?? '—'}</div>
            <div>out: ${out ?? '—'}</div>
          </div>
        );
      },
    },
    {
      header: 'Status',
      cell: ({ row }) => (
        <div className="flex flex-col gap-1">
          {row.original.is_platform_default && (
            <Badge variant="secondary" className="text-[10px] w-fit">Default</Badge>
          )}
          <Badge variant={row.original.is_active ? 'default' : 'outline'} className="text-[10px] w-fit">
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        </div>
      ),
    },
    {
      id: 'actions',
      cell: ({ row }) => (
        <div className="flex gap-1.5 justify-end">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => setEditTarget(row.original)}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-destructive hover:text-destructive"
            onClick={() => {
              if (confirm(`Xoá model "${row.original.name}"?`)) {
                deleteMutation.mutate(row.original.id);
              }
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ),
    },
  ];

  return (
    <section>
      <div className="flex items-end justify-between mb-3.5 gap-3 flex-wrap">
        <div>
          <h2 className="text-[14.5px] font-semibold tracking-tight">Models</h2>
          <p className="text-[12.5px] text-muted-foreground mt-0.5">
            Quản lý danh sách model LLM trong hệ thống.
          </p>
        </div>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          <Plus className="h-3.5 w-3.5" />
          Thêm model
        </Button>
      </div>
      {models.isLoading ? (
        <Skeleton className="h-[220px] rounded-[10px]" />
      ) : (
        <DataTable columns={columns} data={models.data ?? []} />
      )}
      <AddModelDialog open={addOpen} onOpenChange={setAddOpen} />
      {editTarget && (
        <EditModelDialog
          model={editTarget}
          open={!!editTarget}
          onOpenChange={open => { if (!open) setEditTarget(null); }}
        />
      )}
    </section>
  );
}
