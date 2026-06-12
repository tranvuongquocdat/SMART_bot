import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
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
import { useT } from '@/lib/i18n';
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
  const t = useT();
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
      toast.success(t('grp.deleted'));
      setDeleteTarget(null);
    },
    onError: () => toast.error(t('common.deleteError')),
  });

  const enableAllMut = useMutation({
    mutationFn: enableAllGroups,
    onSuccess: (data) => {
      qc.invalidateQueries(groupsListQuery());
      if (data.limit !== null && data.active < data.total) {
        toast.info(
          t('grp.enabledCapped', { active: data.active, total: data.total, limit: data.limit })
        );
      } else {
        toast.success(t('grp.enabledAll', { active: data.active }));
      }
    },
    onError: () => toast.error(t('common.actionFailed')),
  });

  const disableAllMut = useMutation({
    mutationFn: disableAllGroups,
    onSuccess: (data) => {
      qc.invalidateQueries(groupsListQuery());
      toast.success(t('grp.disabledN', { n: data.disabled }));
    },
    onError: () => toast.error(t('common.actionFailed')),
  });

  const toggleMutation = useMutation({
    mutationFn: (id: number) => toggleGroupActive(id),
    onSuccess: (data) => {
      qc.setQueryData(['admin', 'groups'], (old: GroupListItem[] | undefined) =>
        old?.map((g) => (g.id === data.id ? { ...g, is_active: data.is_active } : g)),
      );
      toast.success(data.is_active ? t('grp.toggleOn') : t('grp.toggleOff'));
    },
    onError: (e) => {
      const detail =
        e instanceof ApiError && typeof (e.body as { detail?: string })?.detail === 'string'
          ? (e.body as { detail: string }).detail
          : t('common.actionFailed');
      toast.error(detail);
    },
  });

  const columns: ColumnDef<GroupListItem, any>[] = [
    {
      accessorKey: 'name',
      header: t('grp.col.name'),
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
      header: t('grp.col.channel'),
      cell: ({ getValue }) => <ChannelChip channel={getValue() as string} />,
    },
    {
      accessorKey: 'members_count',
      header: t('grp.col.members'),
      cell: ({ getValue }) => (
        <span className="tabular-nums">{getValue() as number}</span>
      ),
    },
    {
      accessorKey: 'updated_at',
      header: t('grp.col.updated'),
      cell: ({ getValue }) => (
        <span className="text-muted-foreground text-[12.5px]">
          {relativeTime(getValue() as string | null)}
        </span>
      ),
    },
    {
      accessorKey: 'is_active',
      header: t('grp.col.active'),
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
          {t('grp.detail')}
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
          aria-label={t('grp.deleteAria')}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      ),
    },
  ];

  return (
    <PageWrap>
      <PageHeader
        title={t('grp.title')}
        subtitle={t('grp.subtitle')}
        actions={
          <div className="flex gap-2">
            {(data ?? []).some((g) => g.is_active) && (
              <Button
                size="sm"
                variant="outline"
                disabled={disableAllMut.isPending}
                onClick={() => disableAllMut.mutate()}
              >
                {disableAllMut.isPending ? t('grp.disabling') : t('grp.disableAll')}
              </Button>
            )}
            {(data ?? []).some((g) => !g.is_active) && (
              <Button
                size="sm"
                variant="outline"
                disabled={enableAllMut.isPending}
                onClick={() => enableAllMut.mutate()}
              >
                {enableAllMut.isPending ? t('grp.enabling') : t('grp.enableAll')}
              </Button>
            )}
            <Button size="sm" onClick={() => setCreateOpen(true)}>+ {t('grp.create')}</Button>
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
                  title={t('grp.empty.title')}
                  description={t('grp.empty.desc')}
                  action={{ label: `+ ${t('grp.create')}`, onClick: () => setCreateOpen(true) }}
                />
              }
            />
            <AnimatePresence>
              {selectedId && (
                <GroupPanel key={selectedId} id={selectedId} onClose={() => selectGroup(null)} />
              )}
            </AnimatePresence>
          </>
        )}
      </PageSection>

      {/* Dialogs */}
      <CreateGroupDialog open={createOpen} onOpenChange={setCreateOpen} />

      <Dialog open={!!deleteTarget} onOpenChange={v => { if (!v) setDeleteTarget(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('grp.deleteConfirm.title')}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {t('grp.deleteConfirm.desc', { name: deleteTarget?.name ?? '' })}
          </p>
          <DialogFooter className="mt-4">
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>{t('common.cancel')}</Button>
            <Button
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
            >
              {deleteMutation.isPending ? t('common.deleting') : t('common.delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageWrap>
  );
}
