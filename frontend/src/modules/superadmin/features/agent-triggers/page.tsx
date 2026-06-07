import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, MoreHorizontal, Zap } from 'lucide-react';
import { toast } from 'sonner';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/data-table';
import { EmptyState } from '@/components/empty-state';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
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
import { agentTriggersQuery, deleteAgentTrigger, patchAgentTrigger } from './api';
import type { AgentTrigger } from './api';
import { EditDialog } from './edit-dialog';

// ---------------------------------------------------------------------------
// Delete dialog
// ---------------------------------------------------------------------------

function DeleteDialog({
  trigger,
  onClose,
}: {
  trigger: AgentTrigger | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => deleteAgentTrigger(trigger!.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'agent-triggers'] });
      toast.success('Đã xoá trigger');
      onClose();
    },
    onError: () => toast.error('Xoá thất bại'),
  });

  return (
    <Dialog open={trigger !== null} onOpenChange={v => !v && onClose()}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Xoá agent trigger</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground py-2">
          Xoá trigger <strong>{trigger?.op_name}</strong>? Không thể hoàn tác.
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

export default function AgentTriggersPage() {
  const triggers = useQuery(agentTriggersQuery);
  const qc = useQueryClient();

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<AgentTrigger | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AgentTrigger | null>(null);

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      patchAgentTrigger(id, { enabled }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'agent-triggers'] });
    },
    onError: () => toast.error('Cập nhật thất bại'),
  });

  const columns: ColumnDef<AgentTrigger>[] = [
    {
      header: 'Op name',
      accessorKey: 'op_name',
      cell: ({ row }) => (
        <div>
          <div className="font-medium">{row.original.op_name}</div>
          <div className="text-xs text-muted-foreground mt-0.5">{row.original.event_name}</div>
        </div>
      ),
    },
    {
      header: 'Debounce',
      accessorKey: 'debounce_json',
      cell: ({ row }) =>
        row.original.debounce_json ? (
          <pre className="text-xs text-muted-foreground">
            {JSON.stringify(row.original.debounce_json)}
          </pre>
        ) : (
          <span className="text-muted-foreground text-sm">—</span>
        ),
    },
    {
      header: 'Threshold',
      accessorKey: 'threshold_json',
      cell: ({ row }) =>
        row.original.threshold_json ? (
          <pre className="text-xs text-muted-foreground">
            {JSON.stringify(row.original.threshold_json)}
          </pre>
        ) : (
          <span className="text-muted-foreground text-sm">—</span>
        ),
    },
    {
      header: 'Enabled',
      accessorKey: 'enabled',
      cell: ({ row }) => (
        <Switch
          checked={row.original.enabled}
          onCheckedChange={checked =>
            toggleMut.mutate({ id: row.original.id, enabled: checked })
          }
        />
      ),
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
        title="Agent triggers"
        subtitle="Cấu hình debounce, threshold và bật/tắt từng trigger cho agent."
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" />
            Thêm trigger
          </Button>
        }
      />

      <PageSection>
        {triggers.isLoading ? (
          <Skeleton className="h-[220px] rounded-[12px]" />
        ) : (
          <DataTable
            columns={columns}
            data={triggers.data ?? []}
            mobileLabel={col => (typeof col.header === 'string' ? col.header : '')}
            empty={
              <EmptyState
                icon={Zap}
                title="Chưa có trigger nào"
                action={{ label: '+ Thêm trigger', onClick: () => setCreateOpen(true) }}
              />
            }
          />
        )}
      </PageSection>

      <EditDialog trigger={null} open={createOpen} onOpenChange={setCreateOpen} />
      <EditDialog
        trigger={editTarget}
        open={editTarget !== null}
        onOpenChange={v => !v && setEditTarget(null)}
      />
      <DeleteDialog trigger={deleteTarget} onClose={() => setDeleteTarget(null)} />
    </PageWrap>
  );
}
