import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, MoreHorizontal, BookTemplate } from 'lucide-react';
import { toast } from 'sonner';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/data-table';
import { EmptyState } from '@/components/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
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
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { useT, useI18n } from '@/lib/i18n';
import { noteTemplatesQuery, deleteNoteTemplate } from './api';
import type { NoteTemplate } from './api';
import { EditDialog } from './edit-dialog';

// ---------------------------------------------------------------------------
// Delete dialog
// ---------------------------------------------------------------------------

function DeleteDialog({
  template,
  onClose,
}: {
  template: NoteTemplate | null;
  onClose: () => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => deleteNoteTemplate(template!.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'note-templates'] });
      toast.success(t('sa.tmpl.deleted'));
      onClose();
    },
    onError: () => toast.error(t('sa.common.deleteError')),
  });

  return (
    <Dialog open={template !== null} onOpenChange={v => !v && onClose()}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>{t('sa.tmpl.deleteTitle')}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground py-2">
          {t('sa.tmpl.deleteConfirmPre')}<strong>{template?.name}</strong>{t('sa.tmpl.deleteConfirmPost')}
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

export default function NoteTemplatesPage() {
  const { t, lang } = useI18n();
  const locale = lang === 'en' ? 'en-US' : 'vi-VN';
  const templates = useQuery(noteTemplatesQuery);
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<NoteTemplate | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<NoteTemplate | null>(null);

  const columns: ColumnDef<NoteTemplate>[] = [
    {
      header: t('sa.tmpl.colName'),
      accessorKey: 'name',
      cell: ({ row }) => (
        <span className="font-medium">{row.original.name}</span>
      ),
    },
    {
      header: t('sa.tmpl.colDesc'),
      accessorKey: 'description',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">
          {row.original.description ?? '—'}
        </span>
      ),
    },
    {
      header: 'System',
      accessorKey: 'is_system',
      cell: ({ row }) =>
        row.original.is_system ? (
          <span className="text-xs text-muted-foreground">system</span>
        ) : null,
    },
    {
      header: t('sa.tmpl.colUpdated'),
      accessorKey: 'updated_at',
      cell: ({ row }) => {
        const d = row.original.updated_at;
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
              <DropdownMenuItem onClick={() => setEditTarget(row.original)}>
                {t('sa.common.edit')}
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
        title={t('nav.sa.noteTemplates')}
        subtitle={t('sa.tmpl.subtitle')}
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" />
            {t('sa.tmpl.addBtn')}
          </Button>
        }
      />

      <PageSection>
        {templates.isLoading ? (
          <Skeleton className="h-[220px] rounded-[12px]" />
        ) : (
          <DataTable
            columns={columns}
            data={templates.data ?? []}
            mobileLabel={col => (typeof col.header === 'string' ? col.header : '')}
            empty={
              <EmptyState
                icon={BookTemplate}
                title={t('sa.tmpl.empty')}
                action={{ label: t('sa.tmpl.emptyAction'), onClick: () => setCreateOpen(true) }}
              />
            }
          />
        )}
      </PageSection>

      <EditDialog
        template={null}
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
      <EditDialog
        template={editTarget}
        open={editTarget !== null}
        onOpenChange={v => !v && setEditTarget(null)}
      />
      <DeleteDialog template={deleteTarget} onClose={() => setDeleteTarget(null)} />
    </PageWrap>
  );
}
