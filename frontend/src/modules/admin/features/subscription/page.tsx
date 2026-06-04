import { useSuspenseQuery } from '@tanstack/react-query';
import { CreditCard } from 'lucide-react';
import { StatusDot } from '@/components/status-dot';
import { subscriptionQuery } from './api';

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-3 border-b last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{value}</span>
    </div>
  );
}

function planDot(status: string): 'ok' | 'warn' | 'err' | 'idle' {
  if (status === 'active') return 'ok';
  if (status === 'trial') return 'warn';
  if (status === 'expired' || status === 'canceled') return 'err';
  return 'idle';
}

export default function SubscriptionPage() {
  const { data: sub } = useSuspenseQuery(subscriptionQuery());

  const expiresAt = sub.expires_at
    ? new Date(sub.expires_at).toLocaleDateString('vi-VN')
    : '—';

  return (
    <div className="flex flex-col gap-6 p-6 max-w-2xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Gói cước</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Thông tin gói dịch vụ và giới hạn sử dụng.
        </p>
      </div>

      {/* Plan card */}
      <div className="rounded-lg border bg-card">
        <div className="flex items-center gap-3 p-4 border-b">
          <CreditCard className="h-5 w-5 text-muted-foreground" />
          <div>
            <p className="font-semibold capitalize">{sub.plan}</p>
            <p className="text-xs text-muted-foreground">{sub.billing_email}</p>
          </div>
          <div className="ml-auto">
            <StatusDot status={planDot(sub.status)} label={sub.status} />
          </div>
        </div>

        <div className="px-4">
          <InfoRow label="Trạng thái" value={sub.status} />
          <InfoRow label="Gói" value={<span className="capitalize">{sub.plan}</span>} />
          <InfoRow label="Hết hạn" value={expiresAt} />
          <InfoRow
            label="Giới hạn chi phí (USD/ngày)"
            value={`$${sub.cost_cap_usd_daily.toFixed(2)}`}
          />
          <InfoRow
            label="Hóa đơn gần nhất"
            value={sub.last_invoice ?? <span className="text-muted-foreground">—</span>}
          />
        </div>
      </div>

      {/* Upgrade note */}
      <p className="text-xs text-muted-foreground">
        Thanh toán và nâng cấp gói sẽ được tích hợp trong phiên bản tiếp theo.
      </p>
    </div>
  );
}
