import type { ColumnDef } from '@tanstack/react-table';
import { MoreHorizontal } from 'lucide-react';
import { DataTable } from '@/components/data-table';
import { StatusDot } from '@/components/status-dot';
import { Button } from '@/components/ui/button';
import { formatNumber } from '@/lib/format';
import type { BotAccount } from './api';

const STATUS_LABEL: Record<BotAccount['status'], { s: 'ok' | 'warn' | 'err'; label: string }> = {
  online: { s: 'ok', label: 'Online' },
  warn: { s: 'warn', label: 'Cần re-auth' },
  offline: { s: 'err', label: 'Mất kết nối' },
};

const CHANNEL_LABEL: Record<string, string> = {
  zalo: 'Zalo cá nhân',
  telegram: 'Telegram',
  lark: 'Lark',
  web: 'Web',
};

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
    header: 'Kênh',
    accessorKey: 'channel',
    cell: ({ row }) => (
      <span className="inline-flex items-center gap-1.5 px-[7px] py-[1px] rounded text-[11.5px] text-muted-foreground bg-muted font-medium">
        {CHANNEL_LABEL[row.original.channel] ?? row.original.channel}
      </span>
    ),
  },
  {
    header: 'Phân bổ',
    accessorKey: 'assigned_to',
    cell: ({ getValue }) => (
      <span className={getValue() ? '' : 'text-[hsl(var(--dim))]'}>{(getValue() as string) ?? 'Chưa gán'}</span>
    ),
  },
  {
    header: 'Tin nhắn 7d',
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground">
        <b className="font-medium text-foreground">{formatNumber(row.original.messages_in)}</b> in ·{' '}
        <b className="font-medium text-foreground">{formatNumber(row.original.messages_out)}</b> out
      </span>
    ),
  },
  {
    header: 'Trạng thái',
    cell: ({ row }) => {
      const m = STATUS_LABEL[row.original.status];
      return <StatusDot status={m.s} label={m.label} />;
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

export function BotAccountsTable({ data }: { data: BotAccount[] }) {
  return (
    <DataTable
      columns={columns}
      data={data}
      mobileLabel={col => (typeof col.header === 'string' ? col.header : '')}
    />
  );
}
