import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Users, MoreHorizontal } from 'lucide-react';
import type { ColumnDef } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { DataTable } from '@/components/data-table';
import { EmptyState } from '@/components/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { relativeTime } from '@/lib/format';
import { groupsListQuery, deleteGroup, type GroupListItem } from './api';
import { CreateGroupDialog } from './create-dialog';

const CHANNEL_COLOR: Record<string, string> = {
  zalo: 'bg-blue-100 text-blue-700',
  telegram: 'bg-sky-100 text-sky-700',
  lark: 'bg-violet-100 text-violet-700',
  web: 'bg-gray-100 text-gray-600',
};

function ChannelChip({ channel }: { channel: string }) {
  const cls = CHANNEL_COLOR[channel] ?? 'bg-gray-100 text-gray-600';
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11.5px] font-medium ${cls}`}>
      {channel}
    </span>
  );
}

export default function GroupsListPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<GroupListItem | null>(null);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery(groupsListQuery());

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteGroup(id),
    onSuccess: () => {
      qc.invalidateQueries(groupsListQuery());
      toast.success('Đã xoá nhóm');
      setDeleteTarget(null);
    },
    onError: () => toast.error('Xoá thất bại'),
  });

  const columns: ColumnDef<GroupListItem, any>[] = [
    {
      accessorKey: 'name',
      header: 'Tên nhóm',
      cell: ({ row }) => (
        <button
          onClick={() => navigate(`/app/admin/groups/${row.original.id}`)}
          className="font-medium text-left hover:underline text-foreground"
        >
          {row.original.name}
        </button>
      ),
    },
    {
      accessorKey: 'channel',
      header: 'Kênh',
      cell: ({ getValue }) => <ChannelChip channel={getValue() as string} />,
    },
    {
      accessorKey: 'members_count',
      header: 'Thành viên',
      cell: ({ getValue }) => (
        <span className="tabular-nums">{getValue() as number}</span>
      ),
    },
    {
      accessorKey: 'updated_at',
      header: 'Cập nhật',
      cell: ({ getValue }) => (
        <span className="text-muted-foreground text-[12.5px]">
          {relativeTime(getValue() as string | null)}
        </span>
      ),
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-7 w-7 p-0">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => navigate(`/app/admin/groups/${row.original.id}`)}>
              Mở chi tiết
            </DropdownMenuItem>
            <DropdownMenuItem
              className="text-destructive focus:text-destructive"
              onClick={() => setDeleteTarget(row.original)}
            >
              Xoá nhóm
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];

  return (
    <div className="px-10 py-8 max-md:px-4 max-md:py-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Nhóm</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Quản lý các nhóm chat và thành viên
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>+ Tạo nhóm</Button>
      </div>

      {/* Table */}
      {isLoading ? (
        <Skeleton className="h-48 w-full rounded-[10px]" />
      ) : (
        <DataTable
          columns={columns}
          data={data ?? []}
          empty={
            <EmptyState
              icon={Users}
              title="Chưa có nhóm"
              description="Thêm nhóm để bắt đầu theo dõi tin nhắn và tác vụ"
              action={{ label: '+ Tạo nhóm', onClick: () => setCreateOpen(true) }}
            />
          }
        />
      )}

      {/* Dialogs */}
      <CreateGroupDialog open={createOpen} onOpenChange={setCreateOpen} />

      <Dialog open={!!deleteTarget} onOpenChange={v => { if (!v) setDeleteTarget(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Xoá nhóm?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Nhóm <strong>{deleteTarget?.name}</strong> sẽ bị xoá vĩnh viễn. Không thể hoàn tác.
          </p>
          <DialogFooter className="mt-4">
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>Huỷ</Button>
            <Button
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
            >
              {deleteMutation.isPending ? 'Đang xoá…' : 'Xoá'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
