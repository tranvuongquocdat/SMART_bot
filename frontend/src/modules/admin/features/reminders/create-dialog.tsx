import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
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
import { createReminder, remindersQuery } from './api';

export function CreateReminderDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const t = useT();
  const [text, setText] = useState('');
  const [dueAt, setDueAt] = useState('');
  const [scope, setScope] = useState('dm');
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: () =>
      createReminder({
        text: text.trim(),
        due_at: dueAt ? new Date(dueAt).toISOString() : dueAt,
        scope,
      }),
    onSuccess: () => {
      qc.invalidateQueries(remindersQuery('pending'));
      qc.invalidateQueries(remindersQuery('all'));
      toast.success(t('rem.created'));
      setText('');
      setDueAt('');
      setScope('dm');
      onOpenChange(false);
    },
    onError: () => toast.error(t('rem.createError')),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim() || !dueAt) return;
    mutation.mutate();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t('rem.dialog.title')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="reminder-text">{t('rem.field.content')}</Label>
            <Input
              id="reminder-text"
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder={t('rem.field.contentPlaceholder')}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="reminder-due">{t('rem.field.time')}</Label>
            <input
              id="reminder-due"
              type="datetime-local"
              value={dueAt}
              onChange={e => setDueAt(e.target.value)}
              required
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="reminder-scope">{t('rem.field.scope')}</Label>
            <Select value={scope} onValueChange={setScope}>
              <SelectTrigger id="reminder-scope">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="dm">{t('rem.scope.dmFull')}</SelectItem>
                <SelectItem value="group">{t('rem.scope.group')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={mutation.isPending || !text.trim() || !dueAt}
            >
              {mutation.isPending ? t('common.creating') : t('common.create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
