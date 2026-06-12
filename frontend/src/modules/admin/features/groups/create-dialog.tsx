import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useT } from '@/lib/i18n';
import { createGroup, groupsListQuery } from './api';

const CHANNELS = [
  { value: 'zalo', label: 'Zalo' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'lark', label: 'Lark' },
  { value: 'web', label: 'Web' },
];

export function CreateGroupDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const t = useT();
  const [name, setName] = useState('');
  const [channel, setChannel] = useState('zalo');
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => createGroup({ name: name.trim(), channel }),
    onSuccess: () => {
      qc.invalidateQueries(groupsListQuery());
      toast.success(t('grp.created'));
      setName('');
      setChannel('zalo');
      onOpenChange(false);
    },
    onError: () => toast.error(t('grp.createError')),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    mutation.mutate();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t('grp.dialog.title')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="group-name">{t('grp.field.name')}</Label>
            <Input
              id="group-name"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder={t('grp.field.namePlaceholder')}
              autoFocus
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="group-channel">{t('grp.field.channel')}</Label>
            <Select value={channel} onValueChange={setChannel}>
              <SelectTrigger id="group-channel">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CHANNELS.map(c => (
                  <SelectItem key={c.value} value={c.value}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter className="mt-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={!name.trim() || mutation.isPending}>
              {mutation.isPending ? t('grp.creating') : t('grp.create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
