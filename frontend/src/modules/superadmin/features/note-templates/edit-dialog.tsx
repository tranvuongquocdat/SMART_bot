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
import { createNoteTemplate, patchNoteTemplate } from './api';
import type { NoteTemplate } from './api';
import { useT } from '@/lib/i18n';

type Props = {
  template: NoteTemplate | null; // null = create mode
  open: boolean;
  onOpenChange: (v: boolean) => void;
};

export function EditDialog({ template, open, onOpenChange }: Props) {
  const t = useT();
  const qc = useQueryClient();
  const isEdit = template !== null;

  const [form, setForm] = useState({ name: '', description: '' });

  useEffect(() => {
    if (template) {
      setForm({ name: template.name, description: template.description ?? '' });
    } else {
      setForm({ name: '', description: '' });
    }
  }, [template, open]);

  const mutation = useMutation({
    mutationFn: () => {
      if (isEdit) {
        return patchNoteTemplate(template!.id, {
          name: form.name.trim(),
          description: form.description.trim() || null,
        });
      }
      return createNoteTemplate({
        name: form.name.trim(),
        description: form.description.trim() || null,
        sections_json: [],
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['superadmin', 'note-templates'] });
      toast.success(isEdit ? t('sa.tmpl.updated') : t('sa.tmpl.created'));
      onOpenChange(false);
    },
    onError: () => toast.error(isEdit ? t('sa.common.updateError') : t('sa.tmpl.createError')),
  });

  const set = (k: keyof typeof form, v: string) => setForm(f => ({ ...f, [k]: v }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>{isEdit ? t('sa.tmpl.editTitle') : t('sa.tmpl.addTitle')}</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label>{t('sa.tmpl.name')}</Label>
            <Input
              placeholder={t('sa.tmpl.namePlaceholder')}
              value={form.name}
              onChange={e => set('name', e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label>{t('sa.tmpl.descOptional')}</Label>
            <Input
              placeholder={t('sa.tmpl.descPlaceholder')}
              value={form.description}
              onChange={e => set('description', e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('sa.common.cancel')}
          </Button>
          <Button
            disabled={mutation.isPending || !form.name.trim()}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? t('sa.common.saving') : t('sa.common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
