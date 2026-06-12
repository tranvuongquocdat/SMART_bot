import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Network, MoreHorizontal } from 'lucide-react';
import { toast } from 'sonner';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '@/components/data-table';
import { EmptyState } from '@/components/empty-state';
import { StatusDot } from '@/components/status-dot';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
import {
  proxiesQuery,
  createProxy,
  updateProxy,
  deleteProxy,
  testProxy,
  type Proxy,
} from './api';

const STATUS_DOT: Record<string, 'ok' | 'warn' | 'err'> = {
  active: 'ok',
  dead: 'err',
  disabled: 'warn',
};

type FormState = {
  label: string;
  url: string;
  region: string;
  max_bosses: string;
  notes: string;
};

const empty = (): FormState => ({ label: '', url: '', region: '', max_bosses: '1', notes: '' });

function ProxyModal({
  proxy,
  open,
  onClose,
}: {
  proxy: Proxy | null;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<FormState>(empty());
  const isEdit = !!proxy;

  useEffect(() => {
    if (!open) return;
    setForm(
      proxy
        ? {
            label: proxy.label,
            url: '',
            region: proxy.region ?? '',
            max_bosses: String(proxy.max_bosses),
            notes: proxy.notes ?? '',
          }
        : empty()
    );
  }, [open, proxy]);

  const mut = useMutation({
    mutationFn: () => {
      const max_bosses = Number(form.max_bosses) || 1;
      if (isEdit) {
        // url để trống = giữ nguyên url cũ
        return updateProxy(proxy!.id, {
          label: form.label,
          region: form.region,
          max_bosses,
          notes: form.notes,
          ...(form.url.trim() ? { url: form.url.trim() } : {}),
        });
      }
      return createProxy({
        label: form.label,
        url: form.url.trim(),
        region: form.region,
        max_bosses,
        notes: form.notes,
      });
    },
    onSuccess: () => {
      toast.success(isEdit ? 'Đã cập nhật proxy' : 'Đã thêm proxy');
      qc.invalidateQueries({ queryKey: ['superadmin', 'proxies'] });
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const valid = form.label.trim() && (isEdit || form.url.trim());

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-[460px]">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Sửa proxy' : 'Thêm proxy'}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label>Nhãn</Label>
            <Input
              placeholder="VD: VN-HN-01"
              value={form.label}
              onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
            />
          </div>
          <div className="grid gap-1.5">
            <Label>URL {isEdit && <span className="text-xs text-muted-foreground">(để trống = giữ nguyên)</span>}</Label>
            <Input
              placeholder="http://user:pass@host:port hoặc socks5://…"
              value={form.url}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>Vùng</Label>
              <Input
                placeholder="VN / VN-HN / VN-HCM"
                value={form.region}
                onChange={(e) => setForm((f) => ({ ...f, region: e.target.value }))}
              />
            </div>
            <div className="grid gap-1.5">
              <Label>Cap khách (max_bosses)</Label>
              <Input
                type="number"
                min="1"
                value={form.max_bosses}
                onChange={(e) => setForm((f) => ({ ...f, max_bosses: e.target.value }))}
              />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label>Ghi chú</Label>
            <Input
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Huỷ</Button>
          <Button disabled={!valid || mut.isPending} onClick={() => mut.mutate()}>
            {mut.isPending ? 'Đang lưu...' : isEdit ? 'Lưu' : 'Thêm'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function ProxiesPage() {
  const qc = useQueryClient();
  const proxies = useQuery(proxiesQuery);
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Proxy | null>(null);
  const [testing, setTesting] = useState<number | null>(null);

  const delMut = useMutation({
    mutationFn: (id: number) => deleteProxy(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'proxies'] });
      toast.success('Đã xoá proxy');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  async function runTest(p: Proxy) {
    setTesting(p.id);
    try {
      const res = await testProxy(p.id);
      if (res.ok) toast.success(`Proxy sống — IP ra: ${res.ip}`);
      else toast.error(`Proxy lỗi: ${res.message}`);
    } finally {
      setTesting(null);
    }
  }

  const columns: ColumnDef<Proxy>[] = [
    {
      header: 'Proxy',
      accessorKey: 'label',
      cell: ({ row }) => (
        <div>
          <div className="font-medium tracking-tight">{row.original.label}</div>
          <div className="text-[hsl(var(--dim))] text-xs font-mono mt-0.5">
            {row.original.url_masked}
          </div>
        </div>
      ),
    },
    {
      header: 'Vùng',
      accessorKey: 'region',
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground">{row.original.region ?? '—'}</span>
      ),
    },
    {
      header: 'Gán',
      cell: ({ row }) => (
        <span className="text-sm tabular-nums">
          {row.original.assigned_count}/{row.original.max_bosses}
        </span>
      ),
    },
    {
      header: 'Trạng thái',
      cell: ({ row }) => (
        <StatusDot status={STATUS_DOT[row.original.status] ?? 'warn'} label={row.original.status} />
      ),
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
              <DropdownMenuItem disabled={testing === row.original.id} onClick={() => runTest(row.original)}>
                {testing === row.original.id ? 'Đang test…' : 'Test kết nối'}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setEditTarget(row.original)}>Sửa</DropdownMenuItem>
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={() => delMut.mutate(row.original.id)}
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
    <PageWrap className="max-w-[860px]">
      <PageHeader
        title="Proxy"
        subtitle="Pool IP dân cư gán cho từng khách — mọi kênh (Zalo, Messenger) của khách đi qua proxy được gán."
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-3.5 w-3.5 mr-1" />
            Thêm proxy
          </Button>
        }
      />

      <PageSection>
        {proxies.isLoading ? (
          <Skeleton className="h-[220px] rounded-[12px]" />
        ) : (
          <DataTable
            columns={columns}
            data={proxies.data ?? []}
            onRowClick={(p) => setEditTarget(p)}
            mobileLabel={(col) => (typeof col.header === 'string' ? col.header : '')}
            empty={
              <EmptyState
                icon={Network}
                title="Chưa có proxy nào"
                description="Thêm proxy dân cư vào pool rồi gán cho từng khách trong trang Boss."
                action={{ label: '+ Thêm proxy', onClick: () => setCreateOpen(true) }}
              />
            }
          />
        )}
      </PageSection>

      <ProxyModal proxy={null} open={createOpen} onClose={() => setCreateOpen(false)} />
      <ProxyModal proxy={editTarget} open={!!editTarget} onClose={() => setEditTarget(null)} />
    </PageWrap>
  );
}
