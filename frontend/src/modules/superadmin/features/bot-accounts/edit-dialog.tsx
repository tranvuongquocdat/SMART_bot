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
import { patchBotAccount } from './api';
import type { BotAccount } from './api';
import { useT } from '@/lib/i18n';

type Props = {
  account: BotAccount | null;
  onOpenChange: (v: boolean) => void;
};

export function EditDialog({ account, onOpenChange }: Props) {
  const t = useT();
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
      toast.success(t('sa.acct.updated'));
      onOpenChange(false);
    },
    onError: () => toast.error(t('sa.common.updateError')),
  });

  const set = (k: keyof typeof form, v: string) => setForm(f => ({ ...f, [k]: v }));
  const valid = form.label.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>{t('sa.acct.editTitle')}</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label>{t('sa.acct.fieldLabel')}</Label>
            <Input
              value={form.label}
              onChange={e => set('label', e.target.value)}
            />
          </div>

          <div className="grid gap-1.5">
            <Label>{t('sa.acct.fieldKind')}</Label>
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
            <Label>{t('sa.acct.ownership')}</Label>
            <Select value={form.ownership} onValueChange={v => set('ownership', v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="platform">{t('sa.acct.ownPlatform')}</SelectItem>
                <SelectItem value="boss_owned">{t('sa.acct.ownBoss')}</SelectItem>
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
            {mutation.isPending ? t('sa.common.saving') : t('sa.common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
