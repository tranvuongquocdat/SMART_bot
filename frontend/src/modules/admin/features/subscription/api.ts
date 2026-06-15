import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type SubscriptionData = {
  billing_email: string;
  status: string;
  plan: string;
  expires_at: string | null;
  cost_cap_usd_daily: number;
  last_invoice: null;
  upgrade_url: string | null;
};

export type BillingPeriod = '1' | '3' | '12';

export type Plan = {
  id: number;
  name: string;
  label: string;
  limits: {
    max_active_groups: number | null;
    max_active_tools: number | null;
    max_active_channels: number | null;
    mcp_slots: number | null;
    duration_days: number | null;
    cost_cap_usd_daily: number | null;
  };
  prices: Partial<Record<BillingPeriod, number>>;
};

export type SubscriptionRequest = {
  id: number;
  status: string;
  plan_name: string;
  plan_label: string;
  note: string | null;
  amount_paid_vnd: number | null;
  billing_months: number | null;
  reviewer_note: string | null;
  refund_requested: boolean;
  created_at: string;
  reviewed_at: string | null;
  cancelled_at: string | null;
};

export type EffectiveLimits = {
  max_active_groups: number | null;
  max_active_tools: number | null;
  max_active_channels: number | null;
  mcp_slots: number | null;
  cost_cap_usd_daily: number | null;
  over_limit: {
    groups: number;
    tools: number;
    channels: number;
    mcp: number;
    any_over: boolean;
  };
};

export const subscriptionQuery = () =>
  queryOptions({
    queryKey: ['admin', 'subscription'],
    queryFn: () => api<SubscriptionData>('/api/v1/admin/subscription'),
  });

export const plansQuery = () =>
  queryOptions({
    queryKey: ['admin', 'subscription', 'plans'],
    queryFn: () => api<Plan[]>('/api/v1/admin/subscription/plans'),
  });

export const requestsQuery = () =>
  queryOptions({
    queryKey: ['admin', 'subscription', 'requests'],
    queryFn: () => api<SubscriptionRequest[]>('/api/v1/admin/subscription/requests'),
  });

export const limitsQuery = () =>
  queryOptions({
    queryKey: ['admin', 'subscription', 'limits'],
    queryFn: () => api<EffectiveLimits>('/api/v1/admin/subscription/limits'),
  });

function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)smart_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

export async function submitRequest(
  fd: FormData,
): Promise<{ id: number; status: string; plan_name: string }> {
  const res = await fetch('/api/v1/admin/subscription/requests', {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken() },
    body: fd,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? 'Gửi yêu cầu thất bại');
  }
  return res.json();
}

export async function cancelRequest(
  id: number,
  fd: FormData,
): Promise<{ status: string; refund_requested: boolean }> {
  const res = await fetch(`/api/v1/admin/subscription/requests/${id}/cancel`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken() },
    body: fd,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? 'Huỷ thất bại');
  }
  return res.json();
}

export type PaymentInfo = {
  transfer_content: string;
  bank_account_number: string | null;
  bank_account_name: string | null;
  bank_bin: string | null;
};

export const paymentInfoQuery = (planId: number) =>
  queryOptions({
    queryKey: ['admin', 'subscription', 'payment-info', planId],
    queryFn: () =>
      api<PaymentInfo>(`/api/v1/admin/subscription/payment-info?plan_id=${planId}`),
  });
