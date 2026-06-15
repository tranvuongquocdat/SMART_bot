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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useT } from '@/lib/i18n';

function EditBudgetDialog({
  budget,
  open,
  onOpenChange,
}: {
  budget: FeatureBudget;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const t = useT();
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
      toast.success(t('sa.models.budgetUpdated'));
      onOpenChange(false);
    },
    onError: () => toast.error(t('sa.models.budgetUpdateError')),
  });

  const set = (k: keyof typeof form, v: unknown) =>
    setForm(f => ({ ...f, [k]: v }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t('sa.models.budgetEditTitle', { feature: budget.feature })}</DialogTitle>
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
            <Select
              value={form.compression_strategy}
              onValueChange={v => set('compression_strategy', v)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">none</SelectItem>
                <SelectItem value="truncate">truncate</SelectItem>
                <SelectItem value="summarize">summarize</SelectItem>
                <SelectItem value="drop_oldest">drop_oldest</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Cache prefix hint</Label>
            <Input
              value={form.cache_prefix_hint}
              onChange={e => set('cache_prefix_hint', e.target.value)}
              placeholder={t('sa.models.optional')}
            />
          </div>
        </div>
        <DialogFooter className="mt-4">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>{t('sa.common.cancel')}</Button>
          <Button disabled={mutation.isPending} onClick={() => mutation.mutate()}>{t('sa.common.save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function BudgetsTab() {
  const t = useT();
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
          {t('sa.models.budgetsDesc')}
        </p>
      </div>
      {budgets.data?.length === 0 && !budgets.isLoading ? (
        <div className="rounded-[10px] border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          {t('sa.models.budgetsEmpty')}
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
