import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Pencil } from 'lucide-react';
import { toast } from 'sonner';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/data-table';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { llmRoutesQuery, patchLlmRoute } from './api';
import type { LlmRoute } from './api';

function EditRouteDialog({
  route,
  open,
  onOpenChange,
}: {
  route: LlmRoute;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    target_tier: route.target_tier,
    weight: route.weight,
    is_active: route.is_active,
    notes: route.notes ?? '',
  });

  const mutation = useMutation({
    mutationFn: () => patchLlmRoute(route.id, {
      target_tier: form.target_tier,
      weight: Number(form.weight),
      is_active: form.is_active,
      notes: form.notes.trim() || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'llm-routes'] });
      toast.success('Đã cập nhật route');
      onOpenChange(false);
    },
    onError: () => toast.error('Cập nhật route thất bại'),
  });

  const set = (k: keyof typeof form, v: unknown) =>
    setForm(f => ({ ...f, [k]: v }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Sửa route — {route.feature}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3 mt-2">
          <div className="flex flex-col gap-1.5">
            <Label>Target tier</Label>
            <Select value={form.target_tier} onValueChange={v => set('target_tier', v)}>
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
            <Label>Weight</Label>
            <Input
              type="number"
              value={form.weight}
              onChange={e => set('weight', Number(e.target.value))}
            />
          </div>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={e => set('is_active', e.target.checked)}
            />
            Active
          </label>
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

export function RoutesTab() {
  const routes = useQuery(llmRoutesQuery);
  const [editTarget, setEditTarget] = useState<LlmRoute | null>(null);

  const columns: ColumnDef<LlmRoute>[] = [
    {
      header: 'Feature',
      accessorKey: 'feature',
      cell: ({ row }) => (
        <span className="font-mono text-sm">{row.original.feature}</span>
      ),
    },
    {
      header: 'Target tier',
      accessorKey: 'target_tier',
      cell: ({ row }) => (
        <Badge variant="outline" className="capitalize">{row.original.target_tier}</Badge>
      ),
    },
    {
      header: 'Weight',
      accessorKey: 'weight',
      cell: ({ row }) => (
        <span className="text-sm font-mono">{row.original.weight}</span>
      ),
    },
    {
      header: 'Condition',
      accessorKey: 'condition_cel',
      cell: ({ row }) => (
        <span className="text-xs text-muted-foreground font-mono">
          {row.original.condition_cel ?? '—'}
        </span>
      ),
    },
    {
      header: 'Status',
      cell: ({ row }) => (
        <Badge variant={row.original.is_active ? 'default' : 'outline'} className="text-[10px]">
          {row.original.is_active ? 'Active' : 'Inactive'}
        </Badge>
      ),
    },
    {
      id: 'actions',
      cell: ({ row }) => (
        <div className="flex justify-end">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={() => setEditTarget(row.original)}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        </div>
      ),
    },
  ];

  return (
    <section>
      <div className="mb-3.5">
        <h2 className="text-[14.5px] font-semibold tracking-tight">LLM routes</h2>
        <p className="text-[12.5px] text-muted-foreground mt-0.5">
          Mapping feature → tier để điều phối model theo ngữ cảnh.
        </p>
      </div>
      {routes.data?.length === 0 && !routes.isLoading ? (
        <div className="rounded-[10px] border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          Chưa có LLM routes nào. Seed dữ liệu hoặc thêm qua Jinja2 admin.
        </div>
      ) : (
        <DataTable columns={columns} data={routes.data ?? []} />
      )}
      {editTarget && (
        <EditRouteDialog
          route={editTarget}
          open={!!editTarget}
          onOpenChange={open => { if (!open) setEditTarget(null); }}
        />
      )}
    </section>
  );
}
