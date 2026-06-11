import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy } from 'lucide-react';
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
import { submitRequest, paymentInfoQuery } from './api';
import type { Plan } from './api';

function CopyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 px-3 py-2">
      <div className="min-w-0">
        <p className="text-[11px] text-muted-foreground">{label}</p>
        <p className="text-sm font-medium font-mono truncate">{value}</p>
      </div>
      <Button
        size="sm"
        variant="ghost"
        className="h-7 px-2 text-xs shrink-0"
        onClick={() => {
          navigator.clipboard.writeText(value);
          toast.success(`Đã sao chép ${label.toLowerCase()}`);
        }}
      >
        <Copy className="h-3.5 w-3.5 mr-1" />
        Sao chép
      </Button>
    </div>
  );
}

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
  const [customContent, setCustomContent] = useState('');
  const [note, setNote] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const { data: payInfo } = useQuery({
    ...paymentInfoQuery(plan?.id ?? 0),
    enabled: open && plan !== null,
  });

  const mut = useMutation({
    mutationFn: async () => {
      if (!plan) return;
      const fd = new FormData();
      fd.append('plan_id', String(plan.id));
      fd.append('amount_paid_vnd', amount);
      fd.append(
        'transfer_content',
        customContent.trim() || payInfo?.transfer_content || ''
      );
      if (note) fd.append('note', note);
      const file = fileRef.current?.files?.[0];
      if (file) fd.append('payment_proof', file);
      return submitRequest(fd);
    },
    onSuccess: () => {
      toast.success('Đã gửi yêu cầu đăng ký — đang chờ superadmin duyệt');
      qc.invalidateQueries({ queryKey: ['admin', 'subscription'] });
      setAmount('');
      setCustomContent('');
      setNote('');
      if (fileRef.current) fileRef.current.value = '';
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const canSubmit =
    amount && payInfo?.transfer_content && fileRef.current?.files?.length && !mut.isPending;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Đăng ký gói {plan?.label}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {/* Thông tin chuyển khoản — gen sẵn, khách chỉ copy */}
          <div className="rounded-lg border divide-y bg-card">
            {payInfo?.bank_account_number && (
              <CopyRow label="Số tài khoản" value={payInfo.bank_account_number} />
            )}
            {payInfo?.bank_account_name && (
              <div className="px-3 py-2">
                <p className="text-[11px] text-muted-foreground">Chủ tài khoản</p>
                <p className="text-sm font-medium">{payInfo.bank_account_name}</p>
              </div>
            )}
            {payInfo?.transfer_content && (
              <CopyRow label="Nội dung chuyển khoản" value={payInfo.transfer_content} />
            )}
          </div>
          <p className="text-xs text-muted-foreground -mt-2">
            Chuyển khoản đúng nội dung trên để được duyệt nhanh.
          </p>

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
            <Label>Minh chứng chuyển khoản</Label>
            <Input ref={fileRef} type="file" accept=".jpg,.jpeg,.png,.pdf" />
          </div>
          <div className="space-y-1.5">
            <Label>
              Nội dung đã chuyển{' '}
              <span className="text-muted-foreground text-xs">
                (chỉ điền nếu lỡ chuyển khác nội dung trên)
              </span>
            </Label>
            <Input
              value={customContent}
              onChange={(e) => setCustomContent(e.target.value)}
              placeholder={payInfo?.transfer_content ?? ''}
            />
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
