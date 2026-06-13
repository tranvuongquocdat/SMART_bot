import { useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, MoreHorizontal } from 'lucide-react';
import { toast } from 'sonner';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/data-table';
import { StatusDot } from '@/components/status-dot';
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
import { formatNumber } from '@/lib/format';
import { useT } from '@/lib/i18n';
import {
  botAccountsQuery,
  botAccountMessagesQuery,
  deleteBotAccount,
} from './api';
import type { BotAccount, BotMessage } from './api';
import { AccountDrawer, type AccountTabKey } from './account-drawer';
import { ConnectDialog } from './connect-dialog';
import { EditDialog } from './edit-dialog';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';

const STATUS_META: Record<BotAccount['status'], { s: 'ok' | 'warn' | 'err'; labelKey: string }> = {
  online: { s: 'ok', labelKey: 'Online' },
  warn: { s: 'warn', labelKey: 'sa.acct.statusReauth' },
  offline: { s: 'err', labelKey: 'sa.acct.statusOffline' },
};

const CHANNEL_LABEL: Record<string, string> = {
  zalo: 'sa.acct.channelZalo',
  telegram: 'Telegram',
  lark: 'Lark',
  web: 'Web',
};

// ---------------------------------------------------------------------------
// Messages modal
// ---------------------------------------------------------------------------

function MessagesDialog({
  account,
  onClose,
}: {
  account: BotAccount | null;
  onClose: () => void;
}) {
  const t = useT();
  const open = account !== null;
  const msgs = useQuery({
    ...botAccountMessagesQuery(account?.id ?? 0),
    enabled: open,
  });

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{t('sa.acct.msgsTitle', { label: account?.label ?? '' })}</DialogTitle>
        </DialogHeader>

        <div className="min-h-[120px] max-h-[340px] overflow-y-auto">
          {msgs.isLoading && <Skeleton className="h-[120px] rounded-[8px]" />}
          {!msgs.isLoading && (msgs.data ?? []).length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-10">
              {t('sa.acct.msgsEmpty')}
            </p>
          )}
          {(msgs.data ?? []).map((m: BotMessage, i: number) => (
            <div key={i} className="border-b last:border-0 py-2 text-[13px]">
              <span className="text-muted-foreground mr-2">
                {m.direction === 'in' ? '←' : '→'}
              </span>
              {m.text}
              <span className="text-[11px] text-[hsl(var(--dim))] ml-2">{m.created_at}</span>
            </div>
          ))}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('sa.common.close')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Delete confirm modal
// ---------------------------------------------------------------------------

function DeleteDialog({
  account,
  onClose,
}: {
  account: BotAccount | null;
  onClose: () => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const open = account !== null;

  const mutation = useMutation({
    mutationFn: () => deleteBotAccount(account!.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'bot-accounts'] });
      toast.success(t('sa.acct.deleted'));
      onClose();
    },
    onError: () => toast.error(t('sa.common.deleteError')),
  });

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>{t('sa.acct.deleteTitle')}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground py-2">
          {t('sa.acct.deleteConfirmPre')}<strong>{account?.label}</strong>{t('sa.acct.deleteConfirmPost')}
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('sa.common.cancel')}</Button>
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

export default function BotAccountsPage() {
  const t = useT();
  const bots = useQuery(botAccountsQuery);

  const [connectOpen, setConnectOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<BotAccount | null>(null);
  const [msgsTarget, setMsgsTarget] = useState<BotAccount | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<BotAccount | null>(null);
  const [drawer, setDrawer] = useState<{ id: number; tab: AccountTabKey } | null>(null);

  const columns: ColumnDef<BotAccount>[] = [
    {
      header: 'Account',
      accessorKey: 'label',
      cell: ({ row }) => (
        <div>
          <div className="font-medium tracking-tight">{row.original.label}</div>
          <div className="text-[hsl(var(--dim))] text-xs font-mono mt-0.5">{row.original.handle}</div>
        </div>
      ),
    },
    {
      header: t('sa.acct.colChannel'),
      accessorKey: 'channel',
      cell: ({ row }) => (
        <div className="flex flex-col gap-0.5">
          <span className="inline-flex items-center gap-1.5 px-[7px] py-[1px] rounded text-[11.5px] text-muted-foreground bg-muted font-medium w-fit">
            {CHANNEL_LABEL[row.original.channel] ? t(CHANNEL_LABEL[row.original.channel]) : row.original.channel}
          </span>
          <span className="text-[10.5px] text-[hsl(var(--dim))] capitalize">{row.original.account_kind}</span>
        </div>
      ),
    },
    {
      header: t('sa.acct.colOwnership'),
      accessorKey: 'ownership',
      cell: ({ row }) => (
        <span className={row.original.ownership ? '' : 'text-[hsl(var(--dim))]'}>
          {row.original.ownership ?? t('sa.acct.unassigned')}
        </span>
      ),
    },
    {
      header: t('sa.acct.colMessages7d'),
      cell: ({ row }) => (
        <span className="text-xs text-muted-foreground">
          <b className="font-medium text-foreground">{formatNumber(row.original.messages_in)}</b> in ·{' '}
          <b className="font-medium text-foreground">{formatNumber(row.original.messages_out)}</b> out
        </span>
      ),
    },
    {
      header: t('sa.acct.colStatus'),
      cell: ({ row }) => {
        const m = STATUS_META[row.original.status];
        return <StatusDot status={m.s} label={m.labelKey === 'Online' ? 'Online' : t(m.labelKey)} />;
      },
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="text-right" onClick={(e) => e.stopPropagation()}>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-[26px] w-[26px]">
                <MoreHorizontal className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setDrawer({ id: row.original.id, tab: 'overview' })}>
                {t('sa.acct.menuDetail')}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setDrawer({ id: row.original.id, tab: 'connect' })}>
                {t('sa.acct.menuConnect')}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setDrawer({ id: row.original.id, tab: 'messages' })}>
                {t('sa.acct.menuMessages')}
              </DropdownMenuItem>
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
        title={t('sa.models.botAcctCard')}
        subtitle={t('sa.models.botAcctDesc')}
        actions={
          <Button onClick={() => setConnectOpen(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" />
            {t('sa.acct.connectBtn')}
          </Button>
        }
      />

      <PageSection>
        {bots.isLoading ? (
          <Skeleton className="h-[220px] rounded-[12px]" />
        ) : (
          <DataTable
            columns={columns}
            data={bots.data ?? []}
            onRowClick={(acc) => setDrawer({ id: acc.id, tab: 'overview' })}
            mobileLabel={col => (typeof col.header === 'string' ? col.header : '')}
            empty={
              <div className="rounded-[12px] bg-card-grad surface-section p-12 text-center text-muted-foreground text-sm">
                {t('sa.acct.empty')}
              </div>
            }
          />
        )}
      </PageSection>

      <ConnectDialog
        open={connectOpen}
        onOpenChange={setConnectOpen}
        onCreated={(id, provider) =>
          // Acc Zalo tạo xong là mở luôn tab quét QR để đăng nhập
          setDrawer({ id, tab: provider === 'zalo' ? 'connect' : 'overview' })
        }
      />
      <EditDialog account={editTarget} onOpenChange={v => !v && setEditTarget(null)} />
      <MessagesDialog account={msgsTarget} onClose={() => setMsgsTarget(null)} />
      <DeleteDialog account={deleteTarget} onClose={() => setDeleteTarget(null)} />
      <AnimatePresence>
        {drawer && (
          <AccountDrawer
            key={`${drawer.id}-${drawer.tab}`}
            accountId={drawer.id}
            initialTab={drawer.tab}
            onClose={() => setDrawer(null)}
          />
        )}
      </AnimatePresence>
    </PageWrap>
  );
}
