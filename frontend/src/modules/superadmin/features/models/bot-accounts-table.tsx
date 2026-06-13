import type { ColumnDef } from '@tanstack/react-table';
import { MoreHorizontal } from 'lucide-react';
import { DataTable } from '@/components/data-table';
import { StatusDot } from '@/components/status-dot';
import { Button } from '@/components/ui/button';
import { formatNumber } from '@/lib/format';
import { useT } from '@/lib/i18n';
import type { BotAccount } from './api';

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

export function BotAccountsTable({ data }: { data: BotAccount[] }) {
  const t = useT();

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
      cell: () => (
        <div className="text-right">
          <Button variant="ghost" size="icon" className="h-[26px] w-[26px]">
            <MoreHorizontal className="h-3.5 w-3.5" />
          </Button>
        </div>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={data}
      mobileLabel={col => (typeof col.header === 'string' ? col.header : '')}
    />
  );
}
