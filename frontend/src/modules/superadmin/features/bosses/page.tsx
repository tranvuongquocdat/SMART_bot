import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, MoreHorizontal, UserCog } from 'lucide-react';
import { toast } from 'sonner';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/data-table';
import { EmptyState } from '@/components/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
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
import { BossDrawer } from './boss-drawer';
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
  const [detailTarget, setDetailTarget] = useState<Boss | null>(null);

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
      header: 'Gói',
      accessorKey: 'plan_label',
      cell: ({ row }) => (
        <div>
          <span className="text-sm">{row.original.plan_label ?? '—'}</span>
          <span className="block text-[11px] text-muted-foreground capitalize">
            {row.original.subscription_status}
          </span>
        </div>
      ),
    },
    {
      header: 'Hết hạn',
      accessorKey: 'subscription_expiry',
      cell: ({ row }) => {
        const d = row.original.subscription_expiry;
        if (!d) return <span className="text-sm text-muted-foreground">∞</span>;
        const expired = new Date(d) < new Date();
        return (
          <span className={`text-sm ${expired ? 'text-destructive' : 'text-muted-foreground'}`}>
            {new Date(d).toLocaleDateString('vi-VN')}
          </span>
        );
      },
    },
    {
      header: 'Đang dùng',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground tabular-nums">
          {row.original.active_groups} nhóm · {row.original.active_channels} kênh
        </span>
      ),
    },
    {
      header: 'Hoạt động cuối',
      accessorKey: 'last_message_at',
      cell: ({ row }) => {
        const d = row.original.last_message_at;
        if (!d) return <span className="text-sm text-muted-foreground">—</span>;
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
          <div className="text-right" onClick={(e) => e.stopPropagation()}>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-[26px] w-[26px]">
                  <MoreHorizontal className="h-3.5 w-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setDetailTarget(row.original)}>
                  Chi tiết
                </DropdownMenuItem>
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
    <PageWrap>
      <PageHeader
        title="Boss"
        subtitle="Tài khoản người dùng có quyền boss/super-admin trong hệ thống."
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" />
            Thêm boss
          </Button>
        }
      />

      <PageSection>
        {bosses.isLoading ? (
          <Skeleton className="h-[220px] rounded-[12px]" />
        ) : (
          <DataTable
            columns={columns}
            data={bosses.data ?? []}
            onRowClick={setDetailTarget}
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
      </PageSection>

      <CreateDialog open={createOpen} onOpenChange={setCreateOpen} />
      <EditDialog boss={editTarget} onOpenChange={v => !v && setEditTarget(null)} />
      <DeleteDialog boss={deleteTarget} onClose={() => setDeleteTarget(null)} />
      {detailTarget && (
        <BossDrawer boss={detailTarget} onClose={() => setDetailTarget(null)} />
      )}
    </PageWrap>
  );
}
