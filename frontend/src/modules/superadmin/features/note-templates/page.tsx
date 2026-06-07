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
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => deleteNoteTemplate(template!.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'note-templates'] });
      toast.success('Đã xoá template');
      onClose();
    },
    onError: () => toast.error('Xoá thất bại'),
  });

  return (
    <Dialog open={template !== null} onOpenChange={v => !v && onClose()}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Xoá note template</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground py-2">
          Xoá template <strong>{template?.name}</strong>? Không thể hoàn tác.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Huỷ
          </Button>
          <Button
            variant="destructive"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? 'Đang xoá...' : 'Xoá'}
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
  const templates = useQuery(noteTemplatesQuery);
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<NoteTemplate | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<NoteTemplate | null>(null);

  const columns: ColumnDef<NoteTemplate>[] = [
    {
      header: 'Tên',
      accessorKey: 'name',
      cell: ({ row }) => (
        <span className="font-medium">{row.original.name}</span>
      ),
    },
    {
      header: 'Mô tả',
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
      header: 'Cập nhật',
      accessorKey: 'updated_at',
      cell: ({ row }) => {
        const d = row.original.updated_at;
        if (!d) return <span className="text-muted-foreground">—</span>;
        return (
          <span className="text-sm text-muted-foreground">
            {new Date(d).toLocaleString('vi-VN', {
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
                Sửa
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={() => setDeleteTarget(row.original)}
              >
                Xoá
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
        title="Note templates"
        subtitle="Các mẫu ghi chú dùng cho group notes."
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" />
            Thêm template
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
                title="Chưa có template nào"
                action={{ label: '+ Thêm template', onClick: () => setCreateOpen(true) }}
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
