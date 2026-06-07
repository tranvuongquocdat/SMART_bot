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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { patchBoss } from './api';
import type { Boss } from './api';

type Props = {
  boss: Boss | null;
  onOpenChange: (v: boolean) => void;
};

export function EditDialog({ boss, onOpenChange }: Props) {
  const qc = useQueryClient();
  const open = boss !== null;

  const [form, setForm] = useState({
    name: '',
    role: 'boss',
    tz: '',
  });

  useEffect(() => {
    if (boss) {
      setForm({
        name: boss.name ?? '',
        role: boss.role,
        tz: boss.tz,
      });
    }
  }, [boss]);

  const mutation = useMutation({
    mutationFn: () =>
      patchBoss(boss!.id, {
        name: form.name.trim() || null,
        role: form.role,
        tz: form.tz.trim() || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'bosses'] });
      toast.success('Đã cập nhật boss');
      onOpenChange(false);
    },
    onError: () => toast.error('Cập nhật thất bại'),
  });

  const set = (k: keyof typeof form, v: string) => setForm(f => ({ ...f, [k]: v }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>Sửa boss</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label>Tên hiển thị</Label>
            <Input
              value={form.name}
              onChange={e => set('name', e.target.value)}
            />
          </div>

          <div className="grid gap-1.5">
            <Label>Vai trò</Label>
            <Select value={form.role} onValueChange={v => set('role', v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="boss">Boss</SelectItem>
                <SelectItem value="superadmin">Super-admin</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-1.5">
            <Label>Timezone</Label>
            <Input
              placeholder="VD: Asia/Ho_Chi_Minh"
              value={form.tz}
              onChange={e => set('tz', e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Huỷ
          </Button>
          <Button
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? 'Đang lưu...' : 'Lưu'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
