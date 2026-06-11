import { useState, useRef } from 'react';
import { useSuspenseQuery, useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { CreditCard, Clock, X } from 'lucide-react';
import { toast } from 'sonner';
import { StatusDot } from '@/components/status-dot';
import { PageWrap, PageHeader, PageSection } from '@/components/page-shell';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  subscriptionQuery,
  plansQuery,
  requestsQuery,
  limitsQuery,
  cancelRequest,
  type BillingPeriod,
  type Plan,
  type SubscriptionRequest,
} from './api';
import { PlanCards } from './plan-cards';
import { RequestModal } from './request-modal';
import { ResolutionScreen } from './resolution-screen';

function planDot(status: string): 'ok' | 'warn' | 'err' | 'idle' {
  if (status === 'active') return 'ok';
  if (status === 'trial') return 'warn';
  if (status === 'expired' || status === 'canceled') return 'err';
  return 'idle';
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'Đang chờ duyệt',
  approved: 'Đã duyệt',
  rejected: 'Từ chối',
  cancelled: 'Đã huỷ',
};

function CancelModal({
  req,
  open,
  onClose,
}: {
  req: SubscriptionRequest | null;
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [reason, setReason] = useState('');
  const [wantRefund, setWantRefund] = useState(false);
  const qrRef = useRef<HTMLInputElement>(null);

  const mut = useMutation({
    mutationFn: async () => {
      if (!req) return;
      const fd = new FormData();
      fd.append('cancel_reason', reason);
      fd.append('refund_requested', String(wantRefund));
      if (wantRefund) {
        const file = qrRef.current?.files?.[0];
        if (file) fd.append('refund_qr', file);
      }
      return cancelRequest(req.id, fd);
    },
    onSuccess: () => {
      toast.success('Đã huỷ yêu cầu');
      qc.invalidateQueries({ queryKey: ['admin', 'subscription'] });
      setReason('');
      setWantRefund(false);
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Huỷ yêu cầu</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label>Lý do huỷ</Label>
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
            />
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={wantRefund}
              onChange={(e) => setWantRefund(e.target.checked)}
              className="rounded"
            />
            <span className="text-sm">Tôi muốn hoàn tiền</span>
          </label>
          {wantRefund && (
            <div className="space-y-1.5">
              <Label>QR hoàn tiền</Label>
              <Input ref={qrRef} type="file" accept=".jpg,.jpeg,.png" />
            </div>
          )}
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={mut.isPending}>
            Đóng
          </Button>
          <Button
            variant="destructive"
            onClick={() => mut.mutate()}
            disabled={mut.isPending}
          >
            {mut.isPending ? 'Đang huỷ...' : 'Xác nhận huỷ'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function SubscriptionPage() {
  const { data: sub } = useSuspenseQuery(subscriptionQuery());
  const { data: plans = [] } = useQuery(plansQuery());
  const { data: requests = [] } = useQuery(requestsQuery());
  const { data: limits } = useQuery(limitsQuery());

  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
  const [period, setPeriod] = useState<BillingPeriod>('1');
  const [cancelTarget, setCancelTarget] = useState<SubscriptionRequest | null>(null);
  const [warnDismissed, setWarnDismissed] = useState(false);

  const hasPending = requests.some((r) => r.status === 'pending');
  const pendingRequest = requests.find((r) => r.status === 'pending');

  const plansRef = useRef<HTMLDivElement>(null);

  const expiresAt = sub.expires_at
    ? new Date(sub.expires_at).toLocaleDateString('vi-VN')
    : null;

  return (
    <PageWrap className="max-w-[1080px]">
      <PageHeader
        title="Gói cước"
        subtitle="Quản lý gói dịch vụ và giới hạn sử dụng."
      />

      {limits?.over_limit.any_over && !warnDismissed && (
        <ResolutionScreen
          limits={limits}
          onGoToUpgrade={() =>
            plansRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
          }
          onDismiss={() => setWarnDismissed(true)}
        />
      )}

      <PageSection className="rounded-[12px] bg-card-grad surface-section overflow-hidden">
        <div className="flex items-center gap-3 p-4 border-b border-border">
          <CreditCard className="h-5 w-5 text-muted-foreground" />
          <div>
            <p className="font-semibold capitalize">{sub.plan}</p>
            <p className="text-xs text-muted-foreground">{sub.billing_email}</p>
          </div>
          <div className="ml-auto">
            <StatusDot status={planDot(sub.status)} label={sub.status} />
          </div>
        </div>
        <div className="px-4 py-3 text-sm text-muted-foreground">
          {expiresAt ? `Hết hạn: ${expiresAt}` : 'Không giới hạn thời gian'}
        </div>
      </PageSection>

      {hasPending && pendingRequest && (
        <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-sm flex items-center gap-2">
          <Clock className="h-4 w-4 text-yellow-500 shrink-0" />
          <span className="flex-1">
            Yêu cầu đăng ký gói{' '}
            <strong>{pendingRequest.plan_label}</strong> đang chờ duyệt.
          </span>
          <button
            onClick={() => setCancelTarget(pendingRequest)}
            className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
          >
            <X className="h-3 w-3" />
            Huỷ
          </button>
        </div>
      )}

      {plans.length > 0 && (
        <div ref={plansRef}>
          <PageSection>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold">Chọn gói</h2>
              <div className="inline-flex rounded-lg border p-0.5 bg-muted/40">
                {(
                  [
                    { key: '1', label: '1 tháng' },
                    { key: '3', label: '3 tháng' },
                    { key: '12', label: '12 tháng' },
                  ] as { key: BillingPeriod; label: string }[]
                ).map((p) => (
                  <button
                    key={p.key}
                    onClick={() => setPeriod(p.key)}
                    className={`px-3 py-1 text-xs rounded-md transition-colors ${
                      period === p.key
                        ? 'bg-background shadow-sm font-medium'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
            <PlanCards
              plans={plans}
              current={sub}
              hasPending={hasPending}
              period={period}
              onSelect={setSelectedPlan}
            />
          </PageSection>
        </div>
      )}

      {requests.length > 0 && (
        <PageSection>
          <h2 className="text-sm font-semibold mb-3">Lịch sử yêu cầu</h2>
          <div className="divide-y divide-border rounded-xl border">
            {requests.map((req) => (
              <div
                key={req.id}
                className="flex items-center justify-between px-4 py-3 text-sm"
              >
                <div>
                  <span className="font-medium">{req.plan_label}</span>
                  <span className="text-muted-foreground ml-2 text-xs">
                    {new Date(req.created_at).toLocaleDateString('vi-VN')}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge
                    variant={req.status === 'approved' ? 'default' : 'secondary'}
                  >
                    {STATUS_LABELS[req.status] ?? req.status}
                  </Badge>
                  {req.reviewer_note && (
                    <span className="text-xs text-muted-foreground">
                      {req.reviewer_note}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </PageSection>
      )}

      <RequestModal
        plan={selectedPlan}
        period={period}
        open={!!selectedPlan}
        onClose={() => setSelectedPlan(null)}
      />

      <CancelModal
        req={cancelTarget}
        open={!!cancelTarget}
        onClose={() => setCancelTarget(null)}
      />
    </PageWrap>
  );
}
