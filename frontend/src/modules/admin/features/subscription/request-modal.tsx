import { useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { submitRequest } from './api';
import type { Plan } from './api';

export function RequestModal({
  plan,
  open,
  onClose,
}: {
  plan: Plan | null;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [amount, setAmount] = useState('');
  const [content, setContent] = useState('');
  const [note, setNote] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const mut = useMutation({
    mutationFn: async () => {
      if (!plan) return;
      const fd = new FormData();
      fd.append('plan_id', String(plan.id));
      fd.append('amount_paid_vnd', amount);
      fd.append('transfer_content', content);
      if (note) fd.append('note', note);
      const file = fileRef.current?.files?.[0];
      if (file) fd.append('payment_proof', file);
      return submitRequest(fd);
    },
    onSuccess: () => {
      toast.success('Đã gửi yêu cầu đăng ký — đang chờ superadmin duyệt');
      qc.invalidateQueries({ queryKey: ['admin', 'subscription'] });
      setAmount('');
      setContent('');
      setNote('');
      if (fileRef.current) fileRef.current.value = '';
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const canSubmit = amount && content && fileRef.current?.files?.length && !mut.isPending;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Đăng ký gói {plan?.label}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label>Số tiền chuyển khoản (VND)</Label>
            <Input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="490000"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Nội dung chuyển khoản</Label>
            <Input
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="SMART PRO ten_cua_ban"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Minh chứng chuyển khoản</Label>
            <Input ref={fileRef} type="file" accept=".jpg,.jpeg,.png,.pdf" />
          </div>
          <div className="space-y-1.5">
            <Label>
              Ghi chú{' '}
              <span className="text-muted-foreground text-xs">(tuỳ chọn)</span>
            </Label>
            <Textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
            />
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={mut.isPending}>
            Huỷ
          </Button>
          <Button onClick={() => mut.mutate()} disabled={!canSubmit}>
            {mut.isPending ? 'Đang gửi...' : 'Gửi yêu cầu'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
