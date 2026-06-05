import { useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
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
import { patchBotAccount } from './api';
import type { BotAccount } from './api';

type Props = {
  account: BotAccount | null;
  onOpenChange: (v: boolean) => void;
};

export function EditDialog({ account, onOpenChange }: Props) {
  const qc = useQueryClient();
  const open = account !== null;

  const [form, setForm] = useState({
    label: '',
    account_kind: 'personal',
    ownership: 'platform',
  });

  useEffect(() => {
    if (account) {
      setForm({
        label: account.label,
        account_kind: account.account_kind,
        ownership: account.ownership ?? 'platform',
      });
    }
  }, [account]);

  const mutation = useMutation({
    mutationFn: () =>
      patchBotAccount(account!.id, {
        label: form.label.trim(),
        account_kind: form.account_kind,
        ownership: form.ownership || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'bot-accounts'] });
      toast.success('Đã cập nhật account');
      onOpenChange(false);
    },
    onError: () => toast.error('Cập nhật thất bại'),
  });

  const set = (k: keyof typeof form, v: string) => setForm(f => ({ ...f, [k]: v }));
  const valid = form.label.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>Sửa bot account</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label>Tên hiển thị (label)</Label>
            <Input
              value={form.label}
              onChange={e => set('label', e.target.value)}
            />
          </div>

          <div className="grid gap-1.5">
            <Label>Loại tài khoản</Label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={form.account_kind}
              onChange={e => set('account_kind', e.target.value)}
            >
              <option value="personal">Personal</option>
              <option value="official">Official</option>
            </select>
          </div>

          <div className="grid gap-1.5">
            <Label>Ownership</Label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={form.ownership}
              onChange={e => set('ownership', e.target.value)}
            >
              <option value="platform">Platform (dùng chung)</option>
              <option value="boss_owned">Boss owned (riêng)</option>
            </select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Huỷ
          </Button>
          <Button
            disabled={!valid || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? 'Đang lưu...' : 'Lưu'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
