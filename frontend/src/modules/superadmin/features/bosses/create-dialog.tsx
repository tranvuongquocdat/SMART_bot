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
import { createBoss } from './api';

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
};

const INITIAL = {
  email: '',
  name: '',
  role: 'boss',
};

export function CreateDialog({ open, onOpenChange }: Props) {
  const qc = useQueryClient();
  const [form, setForm] = useState(INITIAL);

  const mutation = useMutation({
    mutationFn: () =>
      createBoss({
        email: form.email.trim(),
        name: form.name.trim() || null,
        role: form.role,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'bosses'] });
      toast.success('Đã tạo boss');
      setForm(INITIAL);
      onOpenChange(false);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof Error ? err.message : 'Tạo thất bại';
      toast.error(msg);
    },
  });

  const set = (k: keyof typeof form, v: string) => setForm(f => ({ ...f, [k]: v }));
  const valid = form.email.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>Thêm boss</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label>Email</Label>
            <Input
              type="email"
              placeholder="boss@example.com"
              value={form.email}
              onChange={e => set('email', e.target.value)}
            />
          </div>

          <div className="grid gap-1.5">
            <Label>Tên hiển thị</Label>
            <Input
              placeholder="VD: Nguyễn Văn A"
              value={form.name}
              onChange={e => set('name', e.target.value)}
            />
          </div>

          <div className="grid gap-1.5">
            <Label>Vai trò</Label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={form.role}
              onChange={e => set('role', e.target.value)}
            >
              <option value="boss">Boss</option>
              <option value="superadmin">Super-admin</option>
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
            {mutation.isPending ? 'Đang tạo...' : 'Tạo'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
