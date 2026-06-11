import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Users, Trash2 } from 'lucide-react';
import type { ColumnDef } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { DataTable } from '@/components/data-table';
import { EmptyState } from '@/components/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { relativeTime } from '@/lib/format';
import { ApiError } from '@/lib/api';
import {
  groupsListQuery, deleteGroup, toggleGroupActive,
  enableAllGroups, disableAllGroups, type GroupListItem,
} from './api';
import { CreateGroupDialog } from './create-dialog';
import { GroupPanel } from './group-panel';

function ChannelChip({ channel }: { channel: string }) {
  if (channel === 'zalo') return <Badge variant="zalo">{channel}</Badge>;
  if (channel === 'telegram') return <Badge variant="telegram">{channel}</Badge>;
  return <Badge variant="secondary">{channel}</Badge>;
}

export default function GroupsListPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<GroupListItem | null>(null);
  const qc = useQueryClient();
  const { data, isLoading } = useQuery(groupsListQuery());
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get('g');

  const selectGroup = (id: number | null) => {
    setSearchParams(id === null ? {} : { g: String(id) }, { replace: false });
  };

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteGroup(id),
    onSuccess: () => {
      qc.invalidateQueries(groupsListQuery());
      toast.success('Đã xoá nhóm');
      setDeleteTarget(null);
    },
    onError: () => toast.error('Xoá thất bại'),
  });

  const enableAllMut = useMutation({
    mutationFn: enableAllGroups,
    onSuccess: (data) => {
      qc.invalidateQueries(groupsListQuery());
      if (data.limit !== null && data.active < data.total) {
        toast.info(
          `Đã bật ${data.active}/${data.total} nhóm — gói hiện tại giới hạn ${data.limit} nhóm.`
        );
      } else {
        toast.success(`Đã bật toàn bộ ${data.active} nhóm.`);
      }
    },
    onError: () => toast.error('Thao tác thất bại'),
  });

  const disableAllMut = useMutation({
    mutationFn: disableAllGroups,
    onSuccess: (data) => {
      qc.invalidateQueries(groupsListQuery());
      toast.success(`Đã tắt ${data.disabled} nhóm.`);
    },
    onError: () => toast.error('Thao tác thất bại'),
  });

  const toggleMutation = useMutation({
    mutationFn: (id: number) => toggleGroupActive(id),
    onSuccess: (data) => {
      qc.setQueryData(['admin', 'groups'], (old: GroupListItem[] | undefined) =>
        old?.map((g) => (g.id === data.id ? { ...g, is_active: data.is_active } : g)),
      );
      toast.success(data.is_active ? 'Đã bật nhóm' : 'Đã tắt nhóm');
    },
    onError: (e) => {
      const detail =
        e instanceof ApiError && typeof (e.body as { detail?: string })?.detail === 'string'
          ? (e.body as { detail: string }).detail
          : 'Thao tác thất bại';
      toast.error(detail);
    },
  });

  const columns: ColumnDef<GroupListItem, any>[] = [
    {
      accessorKey: 'name',
      header: 'Tên nhóm',
      cell: ({ row }) => (
        <button
          onClick={() =>
            selectGroup(
              selectedId === String(row.original.id) ? null : row.original.id
            )
          }
          className={`font-medium text-left hover:underline ${
            selectedId === String(row.original.id) ? 'text-primary' : 'text-foreground'
          }`}
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
      accessorKey: 'is_active',
      header: 'Hoạt động',
      cell: ({ row }) => (
        <button
          onClick={() => toggleMutation.mutate(row.original.id)}
          disabled={toggleMutation.isPending && toggleMutation.variables === row.original.id}
          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
            row.original.is_active ? 'bg-primary' : 'bg-input'
          }`}
          role="switch"
          aria-checked={row.original.is_active}
        >
          <span
            className={`pointer-events-none block h-4 w-4 rounded-full bg-background shadow-lg ring-0 transition-transform ${
              row.original.is_active ? 'translate-x-4' : 'translate-x-0'
            }`}
          />
        </button>
      ),
    },
    {
      id: 'detail',
      header: '',
      cell: ({ row }) => (
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={() => selectGroup(row.original.id)}
        >
          Chi tiết
        </Button>
      ),
    },
    {
      id: 'delete',
      header: '',
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
          onClick={() => setDeleteTarget(row.original)}
          aria-label="Xoá nhóm"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      ),
    },
  ];

  return (
    <PageWrap>
      <PageHeader
        title="Nhóm"
        subtitle="Quản lý các nhóm chat và thành viên"
        actions={
          <div className="flex gap-2">
            {(data ?? []).some((g) => g.is_active) && (
              <Button
                size="sm"
                variant="outline"
                disabled={disableAllMut.isPending}
                onClick={() => disableAllMut.mutate()}
              >
                {disableAllMut.isPending ? 'Đang tắt…' : 'Tắt tất cả'}
              </Button>
            )}
            {(data ?? []).some((g) => !g.is_active) && (
              <Button
                size="sm"
                variant="outline"
                disabled={enableAllMut.isPending}
                onClick={() => enableAllMut.mutate()}
              >
                {enableAllMut.isPending ? 'Đang bật…' : 'Bật tất cả'}
              </Button>
            )}
            <Button size="sm" onClick={() => setCreateOpen(true)}>+ Tạo nhóm</Button>
          </div>
        }
      />

      <PageSection>
        {isLoading ? (
          <Skeleton className="h-48 w-full rounded-[12px]" />
        ) : (
          <>
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
            {selectedId && (
              <GroupPanel id={selectedId} onClose={() => selectGroup(null)} />
            )}
          </>
        )}
      </PageSection>

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
    </PageWrap>
  );
}
