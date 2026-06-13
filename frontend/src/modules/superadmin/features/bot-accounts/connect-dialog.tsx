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
import { useT } from '@/lib/i18n';

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
  const t = useT();
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
          ? t('sa.acct.createdZalo')
          : t('sa.acct.connected')
      );
      const provider = form.provider;
      setForm(INITIAL);
      onOpenChange(false);
      onCreated?.(res.id, provider);
    },
    onError: () => toast.error(t('sa.acct.connectError')),
  });

  const set = (k: keyof typeof form, v: string) => setForm(f => ({ ...f, [k]: v }));
  const valid = form.label.trim() && form.handle.trim();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>{t('sa.acct.connectTitle')}</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label>Provider</Label>
            <Select value={form.provider} onValueChange={v => set('provider', v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="zalo">{t('sa.acct.channelZalo')}</SelectItem>
                <SelectItem value="telegram">Telegram</SelectItem>
                <SelectItem value="lark">Lark</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-1.5">
            <Label>{t('sa.acct.fieldLabel')}</Label>
            <Input
              placeholder={t('sa.acct.labelPlaceholder')}
              value={form.label}
              onChange={e => set('label', e.target.value)}
            />
          </div>

          <div className="grid gap-1.5">
            <Label>{t('sa.acct.fieldHandle')}</Label>
            <Input
              placeholder={t('sa.acct.handlePlaceholder')}
              value={form.handle}
              onChange={e => set('handle', e.target.value)}
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
            {mutation.isPending ? t('sa.acct.connecting') : t('sa.acct.connect')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
