import { useState } from 'react';
import { useSuspenseQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, Check, X } from 'lucide-react';
import { toast } from 'sonner';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  subscriptionRequestsQuery,
  approveRequest,
  rejectRequest,
  type SASubscriptionRequest,
} from './api';

const STATUS_LABELS: Record<string, string> = {
  pending: 'Chờ duyệt',
  approved: 'Đã duyệt',
  rejected: 'Từ chối',
  cancelled: 'Đã huỷ',
};

function StatusBadge({ status }: { status: string }) {
  const variant =
    status === 'approved'
      ? 'default'
      : status === 'pending'
        ? 'secondary'
        : 'outline';
  return <Badge variant={variant}>{STATUS_LABELS[status] ?? status}</Badge>;
}

function RejectModal({
  req,
  open,
  onClose,
}: {
  req: SASubscriptionRequest | null;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [note, setNote] = useState('');

  const mut = useMutation({
    mutationFn: () => rejectRequest(req!.id, note),
    onSuccess: () => {
      toast.success('Đã từ chối yêu cầu');
      qc.invalidateQueries({ queryKey: ['superadmin', 'subscription-requests'] });
      setNote('');
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Từ chối yêu cầu</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <p className="text-sm text-muted-foreground">
            Boss: <strong>{req?.boss_email}</strong> — Gói: <strong>{req?.plan_label}</strong>
          </p>
          <div className="space-y-1.5">
            <Label>Lý do từ chối</Label>
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={mut.isPending}>
            Huỷ
          </Button>
          <Button
            variant="destructive"
            onClick={() => mut.mutate()}
            disabled={mut.isPending || !note.trim()}
          >
            {mut.isPending ? 'Đang từ chối...' : 'Xác nhận'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function SASubscriptionsPage() {
  const [filter, setFilter] = useState<string | undefined>('pending');
  const { data: requests } = useSuspenseQuery(subscriptionRequestsQuery(filter));
  const qc = useQueryClient();

  const [rejectTarget, setRejectTarget] = useState<SASubscriptionRequest | null>(null);

  const approveMut = useMutation({
    mutationFn: (id: number) => approveRequest(id),
    onSuccess: () => {
      toast.success('Đã duyệt yêu cầu');
      qc.invalidateQueries({ queryKey: ['superadmin', 'subscription-requests'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const FILTERS = [
    { value: 'pending', label: 'Chờ duyệt' },
    { value: 'approved', label: 'Đã duyệt' },
    { value: 'rejected', label: 'Từ chối' },
    { value: undefined, label: 'Tất cả' },
  ];

  return (
    <PageWrap className="max-w-[900px]">
      <PageHeader
        title="Yêu cầu đăng ký gói"
        subtitle="Duyệt hoặc từ chối yêu cầu nâng cấp gói từ boss."
      />

      <div className="flex gap-2 flex-wrap">
        {FILTERS.map((f) => (
          <button
            key={String(f.value)}
            onClick={() => setFilter(f.value)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              filter === f.value
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted/80'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {requests.length === 0 ? (
        <PageSection>
          <p className="text-sm text-muted-foreground">Không có yêu cầu nào.</p>
        </PageSection>
      ) : (
        <PageSection>
          <div className="divide-y divide-border rounded-xl border">
            {requests.map((req) => (
              <div key={req.id} className="px-4 py-4 space-y-2">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{req.boss_email}</p>
                    <p className="text-xs text-muted-foreground">
                      {req.boss_name} · {req.plan_label}
                      {req.current_plan_name && ` (hiện: ${req.current_plan_name})`}
                    </p>
                  </div>
                  <StatusBadge status={req.status} />
                </div>

                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  {req.amount_paid_vnd && (
                    <span>
                      {req.amount_paid_vnd.toLocaleString('vi-VN')} VND
                    </span>
                  )}
                  {req.transfer_content && <span>· {req.transfer_content}</span>}
                  <span>· {new Date(req.created_at).toLocaleDateString('vi-VN')}</span>
                  {req.refund_qr_path && (
                    <a
                      href={`/api/v1/superadmin/payment-proof/${req.refund_qr_path.split('/').pop()}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 hover:text-foreground"
                    >
                      <ExternalLink className="h-3 w-3" />
                      QR hoàn tiền
                    </a>
                  )}
                </div>

                {req.note && (
                  <p className="text-xs text-muted-foreground italic">Ghi chú: {req.note}</p>
                )}
                {req.reviewer_note && (
                  <p className="text-xs text-muted-foreground">
                    Phản hồi: {req.reviewer_note}
                  </p>
                )}

                {req.status === 'pending' && (
                  <div className="flex gap-2 pt-1">
                    <Button
                      size="sm"
                      onClick={() => approveMut.mutate(req.id)}
                      disabled={approveMut.isPending}
                      className="gap-1"
                    >
                      <Check className="h-3.5 w-3.5" />
                      Duyệt
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setRejectTarget(req)}
                      className="gap-1"
                    >
                      <X className="h-3.5 w-3.5" />
                      Từ chối
                    </Button>
                    {req.refund_qr_path === null && (
                      <a
                        href={`/api/v1/superadmin/payment-proof/${req.id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 ml-auto"
                      >
                        <ExternalLink className="h-3 w-3" />
                        Xem minh chứng
                      </a>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </PageSection>
      )}

      <RejectModal
        req={rejectTarget}
        open={!!rejectTarget}
        onClose={() => setRejectTarget(null)}
      />
    </PageWrap>
  );
}
