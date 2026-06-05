import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, MoreHorizontal, UserCog } from 'lucide-react';
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
import { meQuery } from '@/lib/auth';
import { bossesQuery, deleteBoss } from './api';
import type { Boss } from './api';
import { CreateDialog } from './create-dialog';
import { EditDialog } from './edit-dialog';

// ---------------------------------------------------------------------------
// Role chip
// ---------------------------------------------------------------------------

function RoleChip({ role }: { role: string }) {
  const isSuperadmin = role === 'superadmin';
  return (
    <span
      className={[
        'inline-flex items-center px-[7px] py-[1px] rounded text-[11.5px] font-medium w-fit',
        isSuperadmin
          ? 'bg-primary/10 text-primary'
          : 'bg-muted text-muted-foreground',
      ].join(' ')}
    >
      {isSuperadmin ? 'super-admin' : 'boss'}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Delete confirm dialog
// ---------------------------------------------------------------------------

function DeleteDialog({
  boss,
  onClose,
}: {
  boss: Boss | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const open = boss !== null;

  const mutation = useMutation({
    mutationFn: () => deleteBoss(boss!.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'bosses'] });
      toast.success('Đã xoá boss');
      onClose();
    },
    onError: () => toast.error('Xoá thất bại'),
  });

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Xoá boss</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground py-2">
          Bạn chắc chắn muốn xoá{' '}
          <strong>{boss?.name ?? boss?.email}</strong>? Hành động này không thể hoàn tác.
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

export default function BossesPage() {
  const bosses = useQuery(bossesQuery);
  const me = useQuery(meQuery);

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Boss | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Boss | null>(null);

  const meId = me.data?.id;

  const columns: ColumnDef<Boss>[] = [
    {
      header: 'Tên / Email',
      accessorKey: 'name',
      cell: ({ row }) => (
        <div>
          <div className="font-medium tracking-tight">
            {row.original.name ?? <span className="text-muted-foreground italic">—</span>}
          </div>
          <div className="text-[hsl(var(--dim))] text-xs font-mono mt-0.5">
            {row.original.email}
          </div>
        </div>
      ),
    },
    {
      header: 'Vai trò',
      accessorKey: 'role',
      cell: ({ row }) => <RoleChip role={row.original.role} />,
    },
    {
      header: 'Timezone',
      accessorKey: 'tz',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">{row.original.tz}</span>
      ),
    },
    {
      header: 'Subscription',
      accessorKey: 'subscription_status',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground capitalize">
          {row.original.subscription_status}
        </span>
      ),
    },
    {
      header: 'Tạo lúc',
      accessorKey: 'created_at',
      cell: ({ row }) => {
        const d = row.original.created_at;
        if (!d) return <span className="text-muted-foreground">—</span>;
        return (
          <span className="text-sm text-muted-foreground">
            {new Date(d).toLocaleDateString('vi-VN')}
          </span>
        );
      },
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => {
        const isSelf = row.original.id === meId;
        return (
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
                {!isSelf && (
                  <DropdownMenuItem
                    className="text-destructive focus:text-destructive"
                    onClick={() => setDeleteTarget(row.original)}
                  >
                    Xoá
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        );
      },
    },
  ];

  return (
    <div className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-[1140px]">
      <header className="mb-8">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-[24px] font-semibold tracking-tight">Bosses</h1>
            <p className="text-muted-foreground mt-1.5">
              Tài khoản người dùng có quyền boss/super-admin trong hệ thống.
            </p>
          </div>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" />
            Thêm boss
          </Button>
        </div>
      </header>

      {bosses.isLoading ? (
        <Skeleton className="h-[220px] rounded-[10px]" />
      ) : (
        <DataTable
          columns={columns}
          data={bosses.data ?? []}
          mobileLabel={col => (typeof col.header === 'string' ? col.header : '')}
          empty={
            <EmptyState
              icon={UserCog}
              title="Chưa có boss nào"
              action={{ label: '+ Thêm boss', onClick: () => setCreateOpen(true) }}
            />
          }
        />
      )}

      <CreateDialog open={createOpen} onOpenChange={setCreateOpen} />
      <EditDialog boss={editTarget} onOpenChange={v => !v && setEditTarget(null)} />
      <DeleteDialog boss={deleteTarget} onClose={() => setDeleteTarget(null)} />
    </div>
  );
}
