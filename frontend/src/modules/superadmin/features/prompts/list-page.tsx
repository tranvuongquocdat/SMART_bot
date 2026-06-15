import { useState, type ChangeEvent } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, ExternalLink, MoreHorizontal, FileCode } from 'lucide-react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/data-table';
import { EmptyState } from '@/components/empty-state';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { promptsQuery, createPrompt, deletePrompt, patchPrompt } from './api';
import type { PromptRow } from './api';
import { useT, useI18n } from '@/lib/i18n';

// ---------------------------------------------------------------------------
// Create dialog
// ---------------------------------------------------------------------------

function CreateDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const [form, setForm] = useState({ key: '', body: '', notes: '' });

  const mutation = useMutation({
    mutationFn: () =>
      createPrompt({
        key: form.key.trim(),
        body: form.body,
        notes: form.notes.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'prompts'] });
      toast.success(t('sa.prompt.created'));
      setForm({ key: '', body: '', notes: '' });
      onOpenChange(false);
    },
    onError: () => toast.error(t('sa.prompt.createError')),
  });

  const set = (k: keyof typeof form, v: string) => setForm(f => ({ ...f, [k]: v }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[540px]">
        <DialogHeader>
          <DialogTitle>{t('sa.prompt.addTitle')}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label>Key</Label>
            <Input
              placeholder="vd: dm_general"
              value={form.key}
              onChange={e => set('key', e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label>Body</Label>
            <Textarea
              rows={8}
              className="font-mono text-xs"
              placeholder={t('sa.prompt.bodyPlaceholder')}
              value={form.body}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => set('body', e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label>{t('sa.prompt.notesOptional')}</Label>
            <Input
              placeholder="v1: initial"
              value={form.notes}
              onChange={e => set('notes', e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('sa.common.cancel')}
          </Button>
          <Button
            disabled={mutation.isPending || !form.key.trim() || !form.body.trim()}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? t('sa.common.creating') : t('sa.prompt.createVersion')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Delete confirm
// ---------------------------------------------------------------------------

function DeleteDialog({
  prompt,
  onClose,
}: {
  prompt: PromptRow | null;
  onClose: () => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => deletePrompt(prompt!.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'prompts'] });
      toast.success(t('sa.prompt.deleted'));
      onClose();
    },
    onError: () => toast.error(t('sa.common.deleteError')),
  });

  return (
    <Dialog open={prompt !== null} onOpenChange={v => !v && onClose()}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>{t('sa.prompt.deleteTitle')}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground py-2">
          {t('sa.prompt.deleteConfirmPre')}<strong>{prompt?.key} v{prompt?.version}</strong>{t('sa.prompt.deleteConfirmPost')}
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('sa.common.cancel')}
          </Button>
          <Button
            variant="destructive"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? t('sa.common.deleting') : t('sa.common.delete')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function PromptsListPage() {
  const { t, lang } = useI18n();
  const locale = lang === 'en' ? 'en-US' : 'vi-VN';
  const prompts = useQuery(promptsQuery);
  const qc = useQueryClient();

  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<PromptRow | null>(null);

  const activateMut = useMutation({
    mutationFn: (id: number) => patchPrompt(id, { is_active: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'prompts'] });
      toast.success(t('sa.prompt.activated'));
    },
    onError: () => toast.error(t('sa.prompt.activateError')),
  });

  const columns: ColumnDef<PromptRow>[] = [
    {
      header: 'Key',
      accessorKey: 'key',
      cell: ({ row }) => (
        <Link
          to={`/app/superadmin/prompts/${row.original.id}`}
          className="font-medium text-primary hover:underline flex items-center gap-1"
        >
          {row.original.key}
          <ExternalLink className="h-3 w-3 opacity-60" />
        </Link>
      ),
    },
    {
      header: 'Version',
      accessorKey: 'version',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">v{row.original.version}</span>
      ),
    },
    {
      header: 'Active',
      accessorKey: 'is_active',
      cell: ({ row }) => (
        <Switch
          checked={row.original.is_active}
          onCheckedChange={checked => {
            if (checked) activateMut.mutate(row.original.id);
          }}
        />
      ),
    },
    {
      header: t('sa.prompt.colNotes'),
      accessorKey: 'notes',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground truncate max-w-[200px] block">
          {row.original.notes ?? '—'}
        </span>
      ),
    },
    {
      header: t('sa.prompt.colCreated'),
      accessorKey: 'created_at',
      cell: ({ row }) => {
        const d = row.original.created_at;
        if (!d) return <span className="text-muted-foreground">—</span>;
        return (
          <span className="text-sm text-muted-foreground">
            {new Date(d).toLocaleString(locale, {
              day: '2-digit',
              month: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        );
      },
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="text-right">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-[26px] w-[26px]">
                <MoreHorizontal className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem asChild>
                <Link to={`/app/superadmin/prompts/${row.original.id}`}>{t('sa.prompt.openDetail')}</Link>
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={() => setDeleteTarget(row.original)}
              >
                {t('sa.common.delete')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ),
    },
  ];

  return (
    <PageWrap>
      <PageHeader
        title={t('nav.sa.prompts')}
        subtitle={t('sa.prompt.subtitle')}
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" />
            {t('sa.prompt.addBtn')}
          </Button>
        }
      />

      <PageSection>
        {prompts.isLoading ? (
          <Skeleton className="h-[220px] rounded-[12px]" />
        ) : (
          <DataTable
            columns={columns}
            data={prompts.data ?? []}
            mobileLabel={col => (typeof col.header === 'string' ? col.header : '')}
            empty={
              <EmptyState
                icon={FileCode}
                title={t('sa.prompt.empty')}
                action={{ label: t('sa.prompt.emptyAction'), onClick: () => setCreateOpen(true) }}
              />
            }
          />
        )}
      </PageSection>

      <CreateDialog open={createOpen} onOpenChange={setCreateOpen} />
      <DeleteDialog prompt={deleteTarget} onClose={() => setDeleteTarget(null)} />
    </PageWrap>
  );
}
