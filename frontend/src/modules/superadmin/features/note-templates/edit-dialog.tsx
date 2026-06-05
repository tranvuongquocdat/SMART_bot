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

type Props = {
  template: NoteTemplate | null; // null = create mode
  open: boolean;
  onOpenChange: (v: boolean) => void;
};

export function EditDialog({ template, open, onOpenChange }: Props) {
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
      toast.success(isEdit ? 'Đã cập nhật template' : 'Đã tạo template mới');
      onOpenChange(false);
    },
    onError: () => toast.error(isEdit ? 'Cập nhật thất bại' : 'Tạo thất bại'),
  });

  const set = (k: keyof typeof form, v: string) => setForm(f => ({ ...f, [k]: v }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Sửa note template' : 'Thêm note template'}</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label>Tên</Label>
            <Input
              placeholder="vd: Weekly recap"
              value={form.name}
              onChange={e => set('name', e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label>Mô tả (tuỳ chọn)</Label>
            <Input
              placeholder="Mô tả ngắn..."
              value={form.description}
              onChange={e => set('description', e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Huỷ
          </Button>
          <Button
            disabled={mutation.isPending || !form.name.trim()}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? 'Đang lưu...' : 'Lưu'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
