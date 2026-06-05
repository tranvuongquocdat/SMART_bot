import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Pencil } from 'lucide-react';
import { toast } from 'sonner';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/data-table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { featureBudgetsQuery, patchFeatureBudget } from './api';
import type { FeatureBudget } from './api';

function EditBudgetDialog({
  budget,
  open,
  onOpenChange,
}: {
  budget: FeatureBudget;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    max_input_tokens: budget.max_input_tokens,
    max_output_tokens: budget.max_output_tokens,
    compression_strategy: budget.compression_strategy,
    cache_prefix_hint: budget.cache_prefix_hint ?? '',
  });

  const mutation = useMutation({
    mutationFn: () => patchFeatureBudget(budget.feature, {
      max_input_tokens: Number(form.max_input_tokens),
      max_output_tokens: Number(form.max_output_tokens),
      compression_strategy: form.compression_strategy,
      cache_prefix_hint: form.cache_prefix_hint.trim() || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'feature-budgets'] });
      toast.success('Đã cập nhật budget');
      onOpenChange(false);
    },
    onError: () => toast.error('Cập nhật budget thất bại'),
  });

  const set = (k: keyof typeof form, v: unknown) =>
    setForm(f => ({ ...f, [k]: v }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Sửa budget — {budget.feature}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3 mt-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Max input tokens</Label>
              <Input
                type="number"
                value={form.max_input_tokens}
                onChange={e => set('max_input_tokens', Number(e.target.value))}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Max output tokens</Label>
              <Input
                type="number"
                value={form.max_output_tokens}
                onChange={e => set('max_output_tokens', Number(e.target.value))}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Compression strategy</Label>
            <select
              value={form.compression_strategy}
              onChange={e => set('compression_strategy', e.target.value)}
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="none">none</option>
              <option value="truncate">truncate</option>
              <option value="summarize">summarize</option>
              <option value="drop_oldest">drop_oldest</option>
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Cache prefix hint</Label>
            <Input
              value={form.cache_prefix_hint}
              onChange={e => set('cache_prefix_hint', e.target.value)}
              placeholder="Tùy chọn"
            />
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

export function BudgetsTab() {
  const budgets = useQuery(featureBudgetsQuery);
  const [editTarget, setEditTarget] = useState<FeatureBudget | null>(null);

  const columns: ColumnDef<FeatureBudget>[] = [
    {
      header: 'Feature',
      accessorKey: 'feature',
      cell: ({ row }) => (
        <span className="font-mono text-sm">{row.original.feature}</span>
      ),
    },
    {
      header: 'Max input tokens',
      accessorKey: 'max_input_tokens',
      cell: ({ row }) => (
        <span className="text-sm font-mono">
          {row.original.max_input_tokens.toLocaleString()}
        </span>
      ),
    },
    {
      header: 'Max output tokens',
      accessorKey: 'max_output_tokens',
      cell: ({ row }) => (
        <span className="text-sm font-mono">
          {row.original.max_output_tokens.toLocaleString()}
        </span>
      ),
    },
    {
      header: 'Compression',
      accessorKey: 'compression_strategy',
      cell: ({ row }) => (
        <span className="text-xs text-muted-foreground">
          {row.original.compression_strategy}
        </span>
      ),
    },
    {
      header: 'Cache hint',
      accessorKey: 'cache_prefix_hint',
      cell: ({ row }) => (
        <span className="text-xs text-muted-foreground font-mono">
          {row.original.cache_prefix_hint ?? '—'}
        </span>
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
        <h2 className="text-[14.5px] font-semibold tracking-tight">Feature budgets</h2>
        <p className="text-[12.5px] text-muted-foreground mt-0.5">
          Giới hạn token cho từng feature, chiến lược nén context.
        </p>
      </div>
      {budgets.data?.length === 0 && !budgets.isLoading ? (
        <div className="rounded-[10px] border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          Chưa có feature budgets nào. Seed dữ liệu hoặc thêm qua Jinja2 admin.
        </div>
      ) : (
        <DataTable columns={columns} data={budgets.data ?? []} />
      )}
      {editTarget && (
        <EditBudgetDialog
          budget={editTarget}
          open={!!editTarget}
          onOpenChange={open => { if (!open) setEditTarget(null); }}
        />
      )}
    </section>
  );
}
