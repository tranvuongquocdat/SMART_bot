import { queryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';

export type SASubscriptionRequest = {
  id: number;
  status: string;
  note: string | null;
  amount_paid_vnd: number | null;
  transfer_content: string | null;
  reviewer_note: string | null;
  refund_requested: boolean;
  refund_qr_path: string | null;
  created_at: string;
  reviewed_at: string | null;
  cancelled_at: string | null;
  plan_name: string;
  plan_label: string;
  boss_email: string;
  boss_name: string;
  current_plan_name: string | null;
};

export const subscriptionRequestsQuery = (status?: string) =>
  queryOptions({
    queryKey: ['superadmin', 'subscription-requests', status ?? 'all'],
    queryFn: () =>
      api<SASubscriptionRequest[]>(
        status
          ? `/api/v1/superadmin/subscription-requests?status=${status}`
          : '/api/v1/superadmin/subscription-requests',
      ),
  });

function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)smart_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

async function jsonAction(url: string, body: object): Promise<unknown> {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrfToken(),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? 'Thao tác thất bại');
  }
  return res.json();
}

export function approveRequest(id: number, overrides: Record<string, unknown> = {}) {
  return jsonAction(`/api/v1/superadmin/subscription-requests/${id}/approve`, { overrides });
}

export function rejectRequest(id: number, reviewer_note: string) {
  return jsonAction(`/api/v1/superadmin/subscription-requests/${id}/reject`, { reviewer_note });
}
