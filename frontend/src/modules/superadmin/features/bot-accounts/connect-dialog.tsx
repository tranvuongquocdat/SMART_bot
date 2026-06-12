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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { createBotAccount } from './api';

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated?: (id: number, provider: string) => void;
};

const INITIAL = {
  provider: 'zalo',
  label: '',
  handle: '',
  account_kind: 'personal',
  ownership: 'platform',
};

export function ConnectDialog({ open, onOpenChange, onCreated }: Props) {
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
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'bot-accounts'] });
      toast.success(
        form.provider === 'zalo'
          ? 'Đã tạo account — quét QR để đăng nhập'
          : 'Đã kết nối account'
      );
      const provider = form.provider;
      setForm(INITIAL);
      onOpenChange(false);
      onCreated?.(res.id, provider);
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
            <Select value={form.provider} onValueChange={v => set('provider', v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="zalo">Zalo cá nhân</SelectItem>
                <SelectItem value="telegram">Telegram</SelectItem>
                <SelectItem value="lark">Lark</SelectItem>
              </SelectContent>
            </Select>
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
            <Select value={form.account_kind} onValueChange={v => set('account_kind', v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="personal">Personal</SelectItem>
                <SelectItem value="official">Official</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-1.5">
            <Label>Ownership</Label>
            <Select value={form.ownership} onValueChange={v => set('ownership', v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="platform">Platform (dùng chung)</SelectItem>
                <SelectItem value="boss_owned">Boss owned (riêng)</SelectItem>
              </SelectContent>
            </Select>
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
