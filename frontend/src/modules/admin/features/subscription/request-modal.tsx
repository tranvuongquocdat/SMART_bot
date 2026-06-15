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
import { useT } from '@/lib/i18n';
import { submitRequest, paymentInfoQuery } from './api';
import type { BillingPeriod, Plan } from './api';

const fmtVnd = (v: number) => new Intl.NumberFormat('vi-VN').format(v) + 'đ';

function CopyRow({ label, value, t }: { label: string; value: string; t: (k: string, v?: Record<string, string | number>) => string }) {
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
          toast.success(t('sub.req.copied', { label: label.toLowerCase() }));
        }}
      >
        <Copy className="h-3.5 w-3.5 mr-1" />
        {t('sub.req.copy')}
      </Button>
    </div>
  );
}

export function RequestModal({
  plan,
  period,
  open,
  onClose,
}: {
  plan: Plan | null;
  period: BillingPeriod;
  open: boolean;
  onClose: () => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const [amount, setAmount] = useState('');
  // File input là ref — cần state riêng để nút Gửi re-render khi chọn tệp
  const [hasFile, setHasFile] = useState(false);

  const expectedPrice = plan?.prices?.[period] ?? null;
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
      fd.append('billing_months', period);
      fd.append('amount_paid_vnd', amount || (expectedPrice != null ? String(expectedPrice) : ''));
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
      toast.success(t('sub.req.success'));
      qc.invalidateQueries({ queryKey: ['admin', 'subscription'] });
      setAmount('');
      setCustomContent('');
      setNote('');
      setHasFile(false);
      if (fileRef.current) fileRef.current.value = '';
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const canSubmit =
    (amount || expectedPrice != null) && payInfo?.transfer_content && hasFile && !mut.isPending;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('sub.req.title', { plan: plan?.label ?? '', n: period })}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {expectedPrice != null && (
            <p className="text-sm -mt-1">
              {t('sub.req.amountNeeded')}{' '}
              <span className="font-semibold tabular-nums">{fmtVnd(expectedPrice)}</span>
            </p>
          )}
          {/* Thông tin chuyển khoản — gen sẵn, khách chỉ copy */}
          <div className="rounded-lg border divide-y bg-card">
            {payInfo?.bank_account_number && (
              <CopyRow label={t('sub.req.bankNumber')} value={payInfo.bank_account_number} t={t} />
            )}
            {payInfo?.bank_account_name && (
              <div className="px-3 py-2">
                <p className="text-[11px] text-muted-foreground">{t('sub.req.bankName')}</p>
                <p className="text-sm font-medium">{payInfo.bank_account_name}</p>
              </div>
            )}
            {payInfo?.transfer_content && (
              <CopyRow label={t('sub.req.transferContent')} value={payInfo.transfer_content} t={t} />
            )}
          </div>
          <p className="text-xs text-muted-foreground -mt-2">{t('sub.req.hint')}</p>

          <div className="space-y-1.5">
            <Label>{t('sub.req.amount')}</Label>
            <Input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder={expectedPrice != null ? String(expectedPrice) : '490000'}
            />
          </div>
          <div className="space-y-1.5">
            <Label>{t('sub.req.proof')}</Label>
            <Input
              ref={fileRef}
              type="file"
              accept=".jpg,.jpeg,.png,.pdf"
              onChange={(e) => setHasFile((e.target.files?.length ?? 0) > 0)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>
              {t('sub.req.customContent')}{' '}
              <span className="text-muted-foreground text-xs">
                {t('sub.req.customContentHint')}
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
              {t('sub.req.note')}{' '}
              <span className="text-muted-foreground text-xs">{t('sub.req.noteHint')}</span>
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
            {t('common.cancel')}
          </Button>
          <Button onClick={() => mut.mutate()} disabled={!canSubmit}>
            {mut.isPending ? t('sub.req.submitting') : t('sub.req.submit')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
