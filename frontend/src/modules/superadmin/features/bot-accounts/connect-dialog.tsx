import { useState } from 'react';
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
import { createBotAccount } from './api';

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
};

const INITIAL = {
  provider: 'zalo',
  label: '',
  handle: '',
  account_kind: 'personal',
  ownership: 'platform',
};

export function ConnectDialog({ open, onOpenChange }: Props) {
  const qc = useQueryClient();
  const [form, setForm] = useState(INITIAL);

  const mutation = useMutation({
    mutationFn: () =>
      createBotAccount({
        provider: form.provider,
        label: form.label.trim(),
        handle: form.handle.trim(),
        account_kind: form.account_kind,
        ownership: form.ownership || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'bot-accounts'] });
      toast.success('Đã kết nối account');
      setForm(INITIAL);
      onOpenChange(false);
    },
    onError: () => toast.error('Kết nối thất bại'),
  });

  const set = (k: keyof typeof form, v: string) => setForm(f => ({ ...f, [k]: v }));
  const valid = form.label.trim() && form.handle.trim();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>Kết nối bot account</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label>Provider</Label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={form.provider}
              onChange={e => set('provider', e.target.value)}
            >
              <option value="zalo">Zalo cá nhân</option>
              <option value="telegram">Telegram</option>
              <option value="lark">Lark</option>
            </select>
          </div>

          <div className="grid gap-1.5">
            <Label>Tên hiển thị (label)</Label>
            <Input
              placeholder="VD: Trợ lý Zalo Boss A"
              value={form.label}
              onChange={e => set('label', e.target.value)}
            />
          </div>

          <div className="grid gap-1.5">
            <Label>Handle / ID</Label>
            <Input
              placeholder="VD: 0987654321 hoặc @mybot"
              value={form.handle}
              onChange={e => set('handle', e.target.value)}
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
            {mutation.isPending ? 'Đang kết nối...' : 'Kết nối'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
