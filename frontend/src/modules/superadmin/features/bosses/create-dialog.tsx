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
import { createBoss } from './api';
import { useT } from '@/lib/i18n';

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
  const t = useT();
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
      toast.success(t('sa.boss.created'));
      setForm(INITIAL);
      onOpenChange(false);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof Error ? err.message : t('sa.boss.createError');
      toast.error(msg);
    },
  });

  const set = (k: keyof typeof form, v: string) => setForm(f => ({ ...f, [k]: v }));
  const valid = form.email.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>{t('sa.boss.addTitle')}</DialogTitle>
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
            <Label>{t('sa.boss.fieldName')}</Label>
            <Input
              placeholder={t('sa.boss.namePlaceholder')}
              value={form.name}
              onChange={e => set('name', e.target.value)}
            />
          </div>

          <div className="grid gap-1.5">
            <Label>{t('sa.boss.role')}</Label>
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
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('sa.common.cancel')}
          </Button>
          <Button
            disabled={!valid || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? t('sa.common.creating') : t('sa.common.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
