import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { accountQuery, patchAccount } from './api';

export default function AccountTab() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery(accountQuery);

  const [name, setName] = useState('');

  useEffect(() => {
    if (data) {
      setName(data.name ?? '');
    }
  }, [data]);

  const mut = useMutation({
    mutationFn: () => patchAccount({ name: name || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: accountQuery.queryKey });
      toast.success('Đã lưu tên hiển thị.');
    },
    onError: () => toast.error('Lưu thất bại.'),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Đang tải…</p>;
  if (!data) return null;

  return (
    <div className="space-y-6 max-w-lg">
      {/* Read-only info */}
      <div className="rounded-lg border bg-card p-4 space-y-2 text-sm">
        <div className="flex gap-2">
          <span className="text-muted-foreground w-36">Email</span>
          <span className="font-medium">{data.email}</span>
        </div>
        <div className="flex gap-2">
          <span className="text-muted-foreground w-36">Vai trò</span>
          <span className="font-medium capitalize">{data.role}</span>
        </div>
        <div className="flex gap-2">
          <span className="text-muted-foreground w-36">Google</span>
          <span className="font-medium">{data.google_linked ? 'Đã liên kết' : 'Chưa liên kết'}</span>
        </div>
        <div className="flex gap-2">
          <span className="text-muted-foreground w-36">Gói dịch vụ</span>
          <span className="font-medium">
            {data.subscription_status ?? '—'}
            {data.subscription_expiry && (
              <span className="text-muted-foreground ml-1">
                (hết hạn {new Date(data.subscription_expiry).toLocaleDateString('vi-VN')})
              </span>
            )}
          </span>
        </div>
        <div className="flex gap-2">
          <span className="text-muted-foreground w-36">Cost cap/ngày</span>
          <span className="font-medium">${data.cost_cap_usd_daily.toFixed(2)}</span>
        </div>
      </div>

      {/* Editable: display name */}
      <div className="space-y-2">
        <Label htmlFor="acc-name">Tên hiển thị</Label>
        <Input
          id="acc-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Nhập tên hiển thị"
        />
      </div>

      <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
        {mut.isPending ? 'Đang lưu…' : 'Lưu'}
      </Button>
    </div>
  );
}
